mod compact;
mod observe;
mod policy;
use serde_json::{json, Value};
use std::{env, fs, io::Read};

fn post(url: &str, body: Value, headers: &[(&str, String)]) -> Result<Value, String> {
    let tls = native_tls::TlsConnector::new().map_err(|e| e.to_string())?;
    let agent = ureq::AgentBuilder::new().tls_connector(std::sync::Arc::new(tls)).build();
    let mut r = agent.post(url).set("Content-Type", "application/json");
    for (k, v) in headers {
        r = r.set(k, v);
    }
    r.send_json(body).map_err(|e| e.to_string())?.into_json().map_err(|e| e.to_string())
}

fn forward(payload: &Value) -> Result<String, String> {
    const SYSTEM: &str = "You are the main agent. A fast contrastive pre-screener (CLM) already judged the current state. Treat its verdict as a strong hint, not an order: if route=fast, just execute the suggested action; if route=review, re-check the evidence first. For image_review local_edit, decision.targets is the single most suspicious region and details.region_scores ranks all regions (the true defect was in the top 2 in 15 of 16 calibration cases): verify before editing. Reply with the concrete next step as JSON.";
    let model = env::var("MAIN_MODEL").map_err(|_| "MAIN_MODEL not set")?;
    let user = payload.to_string();
    if env::var("MAIN_PROVIDER").unwrap_or_else(|_| "anthropic".into()) == "anthropic" {
        let base = env::var("MAIN_BASE_URL").unwrap_or_else(|_| "https://api.anthropic.com".into());
        let key = env::var("ANTHROPIC_API_KEY").map_err(|_| "ANTHROPIC_API_KEY not set")?;
        let r = post(
            &format!("{base}/v1/messages"),
            json!({"model": model, "max_tokens": 1024, "system": SYSTEM,
                   "messages": [{"role": "user", "content": user}]}),
            &[("x-api-key", key), ("anthropic-version", "2023-06-01".into())],
        )?;
        Ok(r["content"]
            .as_array()
            .map(|a| a.iter().filter_map(|b| b["text"].as_str()).collect::<String>())
            .unwrap_or_default())
    } else {
        let base = env::var("MAIN_BASE_URL").unwrap_or_else(|_| "https://api.openai.com/v1".into());
        let key = env::var("OPENAI_API_KEY").map_err(|_| "OPENAI_API_KEY not set")?;
        let r = post(
            &format!("{base}/chat/completions"),
            json!({"model": model, "messages": [
                {"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}),
            &[("Authorization", format!("Bearer {key}"))],
        )?;
        if !r["error"].is_null() {
            return Err(format!("main model error: {}", r["error"]["message"].as_str().unwrap_or("unknown")));
        }
        Ok(r["choices"][0]["message"]["content"].as_str().unwrap_or("").to_string())
    }
}

fn run() -> Result<Value, String> {
    let args: Vec<String> = env::args().skip(1).collect();
    let input = args
        .iter()
        .find(|a| !a.starts_with("--"))
        .ok_or("usage: clm-router <req.json|-> [--send]")?;
    let send = args.iter().any(|a| a == "--send");
    let raw = if input == "-" {
        let mut s = String::new();
        std::io::stdin().read_to_string(&mut s).map_err(|e| e.to_string())?;
        s
    } else {
        fs::read_to_string(input).map_err(|e| e.to_string())?
    };
    let req: Value = serde_json::from_str(&raw).map_err(|e| e.to_string())?;

    let base = env::var("CLM_URL").unwrap_or_else(|_| "http://127.0.0.1:8700".into());
    let mode = req["mode"].as_str().unwrap_or("");
    let ask = |state: String, questions: Value| -> Result<Value, String> {
        let resp = post(
            &format!("{}/v1/systemone", base.trim_end_matches('/')),
            json!({"state": state, "questions": questions, "model": "clm-latest", "temperature": 1}),
            &[],
        )?;
        Ok(resp["answers"].clone())
    };
    let low_conf = |d: &policy::Decision| d.reasons.iter().any(|r| r.starts_with("low confidence"));

    let mut steps = vec![];
    #[allow(unused_assignments)] // the empty string is only a placeholder until a branch below sets it
    let mut state_seen = String::new();
    let (answers, d) = match mode {
        "computer_use" => {
            // observe cheapest-first; re-observe with a richer layer while CLM is unsure
            let given = req["observation"]["text"].as_str().map(String::from);
            let shot = req["observation"]["screenshot_path"].as_str().map(String::from);
            let mut start = 0;
            loop {
                let (text, source, layer, tried, errors, _shot) = match &given {
                    Some(t) => (t.clone(), "caller".to_string(), observe::LAYERS.len() - 1, vec![], json!({}), shot.clone()),
                    None => {
                        let o = observe::observe(shot.clone(), start);
                        (o.text, o.source, o.layer, o.tried, o.errors, o.screenshot)
                    }
                };
                let mut r = req.clone();
                r["observation"]["text"] = json!(text);
                state_seen = policy::computer_use_state(&r);
                let answers = ask(state_seen.clone(), policy::computer_use_questions())?;
                let d = policy::decide_computer_use(&answers, &r);
                steps.push(json!({"source": source, "tried": tried, "errors": errors, "chars": text.chars().count()}));
                if !(low_conf(&d) && given.is_none() && layer + 1 < observe::LAYERS.len()) {
                    break (answers, d);
                }
                start = layer + 1;
            }
        }
        "image_review" => {
            let mut r = req.clone();
            let img = &req["image"];
            if img["description"].as_str().unwrap_or("").is_empty()
                && observe::vlm_backend() == Some("online")
            {
                if let Some(path) = img["path"].as_str() {
                    r["image"]["description"] = json!(observe::describe_online(path, observe::IMAGE_PROMPT)?);
                }
            }
            state_seen = policy::image_state(&r);
            let answers = ask(state_seen.clone(), policy::image_questions(&r))?;
            let d = policy::decide_image(&answers, &r);
            (answers, d)
        }
        m => return Err(format!("unknown mode {m:?}")),
    };
    let mut out = json!({"decision": d.to_json(), "clm_raw": answers, "observation_steps": steps});
    if let Ok(path) = env::var("CLM_TRAJECTORY_LOG") {
        // opt-in: exactly what CLM saw and answered, `label` left empty for a human (the data fine-tuning needs). Keep the file private.
        let rec = json!({"ts": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|t| t.as_secs_f64()).unwrap_or(0.0),
                         "mode": mode, "task": req["task"], "history": req["history"], "last_action": req["last_action"],
                         "state": state_seen, "answers": out["clm_raw"], "decision": out["decision"], "label": null});
        use std::io::Write;
        if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(&path) {
            let _ = writeln!(f, "{rec}");
        }
    }
    if send {
        let payload = json!({"mode": mode, "task": req["task"], "clm_decision": out["decision"],
                             "clm_raw": out["clm_raw"], "context": req});
        out["main_reply"] = json!(forward(&payload)?);
    }
    Ok(out)
}

fn main() {
    match run() {
        Ok(v) => println!("{}", serde_json::to_string_pretty(&v).unwrap()),
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    }
}
