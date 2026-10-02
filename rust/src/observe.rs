//! Observation layer (mirror of python/clm_router/observe.py): a11y -> ocr -> vlm, cheapest first.
use base64::Engine;
use serde_json::{json, Value};
use std::{env, fs, path::PathBuf, process::Command};

pub const LAYERS: [&str; 3] = ["a11y", "ocr", "vlm"];
const MIN_CHARS: [usize; 3] = [80, 40, 1];
const ONLINE_MODEL: &str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free";
const UI_PROMPT: &str = "You are reading a computer screenshot for an automation agent. List the visible app/window, dialogs, buttons, inputs, menus and any error text, one per line as: role \"label\" @(x,y) in pixels of the image. Then one line starting 'STATE:' summarising what the screen shows. Be concise.";
pub const IMAGE_PROMPT: &str = "Describe this generated image for a QA reviewer: subject, composition, style, any text exactly as written, and visible defects (hands, faces, artifacts). Then list regions as: [id] description.";

pub struct Observation {
    pub text: String,
    pub source: String,
    pub layer: usize, // last layer that ran successfully
    pub tried: Vec<String>,
    pub errors: Value,
    pub screenshot: Option<String>,
}

fn scripts() -> PathBuf {
    env::var("CLM_SCRIPTS")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../scripts"))
}

fn run(cmd: &str, args: &[String]) -> Result<String, String> {
    let o = Command::new(cmd).args(args).output().map_err(|e| format!("{cmd}: {e}"))?;
    if !o.status.success() {
        let err: String = String::from_utf8_lossy(&o.stderr).trim().chars().take(200).collect();
        return Err(format!("{cmd}: {err}"));
    }
    Ok(String::from_utf8_lossy(&o.stdout).into_owned())
}

fn ps(script: &str, extra: &[String]) -> Result<String, String> {
    let mut a: Vec<String> = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"].map(String::from).to_vec();
    a.push(scripts().join(script).to_string_lossy().into_owned());
    a.extend_from_slice(extra);
    run("powershell", &a)
}

fn has(tool: &str) -> bool {
    Command::new(if cfg!(windows) { "where" } else { "which" })
        .arg(tool)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn screenshot() -> Result<String, String> {
    let out = env::temp_dir().join(format!("clm_screen_{}.png", std::process::id())).to_string_lossy().into_owned();
    if cfg!(windows) {
        ps("screenshot.ps1", &[out.clone()])?;
    } else {
        let cands: [(&str, Vec<String>); 4] = [
            ("grim", vec![out.clone()]),
            ("scrot", vec!["-o".into(), out.clone()]),
            ("import", vec!["-window".into(), "root".into(), out.clone()]),
            ("gnome-screenshot", vec!["-f".into(), out.clone()]),
        ];
        let (tool, args) = cands
            .iter()
            .find(|(t, _)| has(t))
            .ok_or("no screenshot tool (grim/scrot/imagemagick/gnome-screenshot)")?;
        run(tool, args)?;
    }
    Ok(out)
}

fn png_size(path: &str) -> Result<(f64, f64), String> {
    let b = fs::read(path).map_err(|e| e.to_string())?;
    if b.len() < 24 {
        return Err("not a png".into());
    }
    let w = u32::from_be_bytes([b[16], b[17], b[18], b[19]]);
    let h = u32::from_be_bytes([b[20], b[21], b[22], b[23]]);
    Ok((w as f64, h as f64))
}

fn post(url: &str, body: Value, auth: Option<String>) -> Result<Value, String> {
    let tls = native_tls::TlsConnector::new().map_err(|e| e.to_string())?;
    let agent = ureq::AgentBuilder::new().tls_connector(std::sync::Arc::new(tls)).build();
    let mut r = agent.post(url).set("Content-Type", "application/json");
    if let Some(a) = auth {
        r = r.set("Authorization", &a);
    }
    r.send_json(body).map_err(|e| e.to_string())?.into_json().map_err(|e| e.to_string())
}

fn b64(path: &str) -> Result<String, String> {
    Ok(base64::engine::general_purpose::STANDARD.encode(fs::read(path).map_err(|e| e.to_string())?))
}

fn omniparser(img: &str) -> Result<String, String> {
    let url = env::var("OMNIPARSER_URL").map_err(|_| "OMNIPARSER_URL not set")?;
    let (w, h) = png_size(img)?;
    let r = post(&format!("{}/parse/", url.trim_end_matches('/')), json!({"base64_image": b64(img)?}), None)?;
    let mut lines = vec![];
    for (i, it) in r["parsed_content_list"].as_array().cloned().unwrap_or_default().iter().enumerate() {
        let bb: Vec<f64> = it["bbox"]
            .as_array()
            .map(|a| a.iter().map(|v| v.as_f64().unwrap_or(0.0)).collect())
            .unwrap_or_default();
        if bb.len() < 4 {
            continue;
        }
        // bbox is normalised xyxy -> centre in pixels
        let (x, y) = (((bb[0] + bb[2]) / 2.0 * w) as i64, ((bb[1] + bb[3]) / 2.0 * h) as i64);
        let kind = if it["interactivity"].as_bool().unwrap_or(false) { "clickable" } else { it["type"].as_str().unwrap_or("element") };
        lines.push(format!("[{i}] {kind} \"{}\" @({x},{y})", it["content"].as_str().unwrap_or("").trim()));
    }
    Ok(lines.join("\n"))
}

pub fn describe_online(img: &str, prompt: &str) -> Result<String, String> {
    let key = env::var("OPENROUTER_API_KEY").map_err(|_| "OPENROUTER_API_KEY not set")?;
    let base = env::var("OPENROUTER_BASE_URL").unwrap_or_else(|_| "https://openrouter.ai/api/v1".into());
    let model = env::var("OBS_ONLINE_MODEL").unwrap_or_else(|_| ONLINE_MODEL.into());
    let r = post(
        &format!("{base}/chat/completions"),
        json!({"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": format!("data:image/png;base64,{}", b64(img)?)}}]}]}),
        Some(format!("Bearer {key}")),
    )?;
    let t = r["choices"][0]["message"]["content"].as_str().unwrap_or("");
    // drop <think>...</think> blocks
    let (mut out, mut rest) = (String::new(), t);
    while let Some(s) = rest.find("<think>") {
        out.push_str(&rest[..s]);
        rest = match rest[s..].find("</think>") {
            Some(e) => &rest[s + e + 8..],
            None => "",
        };
    }
    out.push_str(rest);
    Ok(out.trim().to_string())
}

/// A Chromium/Edge window whose accessibility tree has the browser UI but no web `Document`: the page itself is invisible.
pub fn browser_without_content(a11y: &str) -> bool {
    if !a11y.contains("Google Chrome") && !a11y.contains("Microsoft Edge") {
        return false;
    }
    let lines: Vec<&str> = a11y.lines().collect();
    let indent = |l: &str| l.len() - l.trim_start().len();
    for (i, line) in lines.iter().enumerate() {
        if line.trim_start().starts_with("Document") {
            // Chrome builds the page tree lazily: Document can exist with no children
            let kids = lines[i + 1..].iter().take_while(|n| indent(n) > indent(line)).count();
            return kids < 5;
        }
    }
    true
}

pub fn vlm_backend() -> Option<&'static str> {
    match env::var("OBS_VLM").as_deref() {
        Ok("local") if env::var("OMNIPARSER_URL").is_ok() => Some("local"),
        Ok("online") if env::var("OPENROUTER_API_KEY").is_ok() => Some("online"),
        _ => None,
    }
}

fn run_layer(name: &str, screenshot_slot: &mut Option<String>) -> Result<String, String> {
    if name == "vlm" && vlm_backend().is_none() {
        return Err("no VLM configured (set OBS_VLM=local+OMNIPARSER_URL or online+OPENROUTER_API_KEY)".into());
    }
    if name != "a11y" && screenshot_slot.is_none() {
        *screenshot_slot = Some(screenshot()?);
    }
    let img = screenshot_slot.clone().unwrap_or_default();
    match name {
        "a11y" => {
            if cfg!(windows) {
                // OBS_WINDOW_TITLE: read this window instead of whichever one is in the foreground
                let mut a: Vec<String> = vec![];
                if let Ok(h) = env::var("OBS_WINDOW_HWND") {
                    a.extend(["-Hwnd".to_string(), h]); // exact window handle wins over the title
                } else if let Ok(t) = env::var("OBS_WINDOW_TITLE") {
                    a.extend(["-Title".to_string(), t]);
                }
                a.extend(["-MaxNodes".to_string(), env::var("OBS_MAX_NODES").unwrap_or_else(|_| "300".into())]);
                a.extend(["-MaxDepth".to_string(), env::var("OBS_MAX_DEPTH").unwrap_or_else(|_| "24".into())]); // web pages sit deep in the tree
                ps("uia_dump.ps1", &a)
            } else {
                run("python3", &[scripts().join("atspi_dump.py").to_string_lossy().into_owned()])
            }
        }
        "ocr" => {
            if cfg!(windows) {
                ps("ocr.ps1", &[img])
            } else if has("tesseract") {
                let lang = env::var("TESSERACT_LANG").unwrap_or_else(|_| "eng".into());
                run("tesseract", &[img, "stdout".into(), "-l".into(), lang])
            } else {
                Err("tesseract not installed".into())
            }
        }
        _ => {
            if vlm_backend() == Some("local") {
                omniparser(&img)
            } else {
                describe_online(&img, UI_PROMPT)
            }
        }
    }
}

/// Try layers from `start`; stop at the first one that yields enough text.
pub fn observe(given_screenshot: Option<String>, start: usize) -> Observation {
    let mut o = Observation {
        text: String::new(),
        source: String::new(),
        layer: start.wrapping_sub(1),
        tried: vec![],
        errors: json!({}),
        screenshot: given_screenshot,
    };
    for idx in start..LAYERS.len() {
        let name = LAYERS[idx];
        let res = run_layer(name, &mut o.screenshot);
        o.tried.push(name.to_string());
        match res {
            Err(e) => o.errors[name] = json!(e.chars().take(200).collect::<String>()),
            Ok(t) => {
                let mut t = t.trim().to_string();
                let mut label = if name == "vlm" { format!("vlm_{}", vlm_backend().unwrap_or("?")) } else { name.to_string() };
                if name == "a11y" && browser_without_content(&t) {
                    // page content is not exposed by the browser: add OCR, page text first
                    match run_layer("ocr", &mut o.screenshot) {
                        Ok(ocr) => {
                            t = format!("--- page content (OCR; x,y are screen pixels) ---
{}
--- browser UI (accessibility tree) ---
{}", ocr.trim(), t);
                            label = "a11y+ocr".into();
                        }
                        Err(e) => o.errors["a11y+ocr"] = json!(e.chars().take(200).collect::<String>()),
                    }
                }
                o.layer = idx;
                let enough = t.chars().count() >= MIN_CHARS[idx];
                if t.len() > o.text.len() {
                    o.source = label;
                    o.text = t;
                }
                if enough {
                    break;
                }
            }
        }
    }
    o
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn browser_without_document_needs_ocr() {
        let ui = "Window \"Google Flow - Google Chrome\" @(0,0,10x10)
  Button \"x\" @(1,1,1x1)";
        assert!(browser_without_content(ui));
        let empty = format!("{ui}
    Document \"Flow\" @(0,0,1x1)
    Button \"tab\" @(0,0,1x1)");
        assert!(browser_without_content(&empty)); // Document with no children yet
        let full = format!("{ui}
    Document \"Flow\" @(0,0,1x1)") + &(0..6).map(|i| format!("
        Text \"t{i}\" @(0,0,1x1)")).collect::<String>();
        assert!(!browser_without_content(&full));
        assert!(!browser_without_content("Window \"Notepad\" @(0,0,1x1)"));
    }
}
