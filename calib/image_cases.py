"""Image-review calibration set: 16 briefs x 3 outcomes (pass / local_edit / regenerate) = 48 cases, written by the
assistant. Each case is what the pipeline would hand to CLM: the brief, must-have criteria, a VLM-style text
description of the produced image, and per-region descriptions. Run:  python calib/image_cases.py

local_edit: exactly one region violates a criterion (`bad` lists it). regenerate: the image is wrong as a whole.
Labels are the assistant's own judgement (no independent annotator).
"""
import json
from pathlib import Path

# name, brief, criteria, ok-regions {id: desc}, ok description,
# (bad region id, its faulty description, faulty full description),
# (regenerate full description, regenerate regions {id: desc})
BRIEFS = [
    ("poster", "Minimal poster, text 'OPEN DAILY 8-5', a latte cup in the centre",
     ["text reads exactly OPEN DAILY 8-5", "one latte cup centred", "flat pastel style"],
     {"headline": "text reads 'OPEN DAILY 8-5'", "cup": "one latte cup with heart foam art, centred"},
     "Flat pastel poster. A single latte cup with heart foam art sits in the centre. The headline reads 'OPEN DAILY 8-5' in rounded sans-serif.",
     ("headline", "text reads 'OPEN DAILY 8-S'", "Flat pastel poster. A single latte cup with heart foam art sits in the centre. The headline reads 'OPEN DAILY 8-S' in rounded sans-serif."),
     ("Dark photographic image of a rainy city street at night. No cup anywhere. Blurry neon letters that do not form words.",
      {"headline": "illegible blurry neon letters", "cup": "no cup present"})),
    ("portrait", "Photoreal portrait of an elderly fisherman with a net, warm light",
     ["one person, elderly man", "fishing net visible", "photoreal, warm light", "five fingers on each hand"],
     {"face": "weathered face with grey beard, natural", "hands": "two hands holding the net, five fingers each"},
     "Photoreal portrait of an elderly man with a weathered face and grey beard holding a fishing net, warm golden light, both hands show five fingers.",
     ("hands", "left hand has six fingers", "Photoreal portrait of an elderly man with a weathered face and grey beard holding a fishing net, warm golden light, the left hand shows six fingers."),
     ("Flat-colour cartoon drawing of a young woman in a red dress. No net, no elderly man, not photographic.",
      {"face": "cartoon young woman", "hands": "hands not visible"})),
    ("logo", "Logo for 'Nimbus Cloud', blue gradient cloud icon with the wordmark underneath",
     ["wordmark spells Nimbus Cloud", "blue gradient cloud icon", "clean vector style"],
     {"icon": "blue gradient cloud icon, clean edges", "wordmark": "text reads 'Nimbus Cloud'"},
     "Clean vector logo: a blue gradient cloud icon with the wordmark 'Nimbus Cloud' underneath.",
     ("wordmark", "text reads 'Nimbus Cluod'", "Clean vector logo: a blue gradient cloud icon with the wordmark 'Nimbus Cluod' underneath."),
     ("Photograph of a real grey cloud over mountains. No icon, no text, not a logo.",
      {"icon": "photographic cloud, no icon", "wordmark": "no text present"})),
    ("sneaker", "Product photo of one white sneaker on a plain white background",
     ["exactly one sneaker", "plain white background", "brand logo sharp and readable"],
     {"shoe": "single white sneaker, three-quarter view", "logo": "sharp swoosh-style logo on the side", "background": "plain white"},
     "Studio product photo of a single white sneaker on a plain white background; the side logo is sharp.",
     ("logo", "side logo is smeared and unreadable", "Studio product photo of a single white sneaker on a plain white background; the side logo is smeared and unreadable."),
     ("Three different shoes scattered on a cluttered wooden table in a messy room, shot at a tilt.",
      {"shoe": "three different shoes", "logo": "logos not visible", "background": "cluttered room, not white"})),
    ("landscape", "Mountain lake at sunrise, calm water, clear sky, no people or buildings",
     ["mountain lake at sunrise", "calm reflective water", "clear sky", "no people or buildings"],
     {"sky": "clear pastel sunrise sky", "lake": "calm lake mirroring the mountains", "shore": "empty shoreline with pines"},
     "Mountain lake at sunrise with calm mirror-like water, a clear pastel sky and an empty pine shoreline.",
     ("sky", "a small white rectangular blob floats in the sky", "Mountain lake at sunrise with calm mirror-like water, an empty pine shoreline and a small white rectangular blob floating in the sky."),
     ("Extremely blurry low-resolution image, only vague brown and grey shapes, nothing identifiable, heavy compression blocks.",
      {"sky": "blurry grey area", "lake": "indistinguishable", "shore": "indistinguishable"})),
    ("icons", "Set of four app icons in the same outline style: home, search, heart, user",
     ["four icons: home, search, heart, user", "all in the same outline style", "same stroke width"],
     {"icon1": "outline home", "icon2": "outline magnifier", "icon3": "outline heart", "icon4": "outline user"},
     "Four app icons in a row, all outline style with equal stroke width: home, search, heart, user.",
     ("icon3", "solid filled heart instead of outline", "Four app icons in a row: outline home, outline search, a solid filled heart, outline user."),
     ("One large detailed illustration of a rocket launching, full colour. No icon grid.",
      {"icon1": "none", "icon2": "none", "icon3": "none", "icon4": "none"})),
    ("ui", "Mobile login screen mockup with an Email field and a 'Sign in' button",
     ["Email input field", "button labelled Sign in", "mobile screen layout"],
     {"field": "Email input field", "button": "button reads 'Sign in'"},
     "Mobile login screen with an Email input field and a button that reads 'Sign in'.",
     ("button", "button reads 'Sing in'", "Mobile login screen with an Email input field and a button that reads 'Sing in'."),
     ("Photograph of a laptop on a desk whose blurred screen shows nothing readable. Not a mobile mockup.",
      {"field": "not present", "button": "not present"})),
    ("chart", "Bar chart with three bars labelled Q1, Q2, Q3 rising left to right",
     ["three bars", "labels Q1 Q2 Q3", "bars rise left to right"],
     {"bars": "three bars of increasing height", "label1": "Q1", "label2": "Q2", "label3": "Q3"},
     "Bar chart with three bars of increasing height labelled Q1, Q2 and Q3.",
     ("label2", "second label reads 'Q5'", "Bar chart with three bars of increasing height labelled Q1, Q5 and Q3."),
     ("Hand-drawn pie chart with clashing neon colours and unreadable scribbled labels. No bars.",
      {"bars": "no bars, a pie chart", "label1": "scribble", "label2": "scribble", "label3": "scribble"})),
    ("book", "Children's book illustration of a cat reading a book in an armchair",
     ["one cat", "cat has four legs and one tail", "reading a book", "armchair"],
     {"cat": "cat with four legs and one tail", "book": "open book held by the cat", "chair": "red armchair"},
     "Soft watercolour of a cat with four legs and one tail reading an open book in a red armchair.",
     ("cat", "the cat has five legs", "Soft watercolour of a cat with five legs reading an open book in a red armchair."),
     ("Realistic photograph of a dog sleeping on a lawn. No book, no armchair, no cat.",
      {"cat": "a dog, not a cat", "book": "none", "chair": "none"})),
    ("ramen", "Photo of a bowl of ramen with a soft-boiled egg and chopsticks",
     ["bowl of ramen", "soft-boiled egg visible", "chopsticks"],
     {"bowl": "bowl of ramen with noodles", "egg": "halved soft-boiled egg", "chopsticks": "wooden chopsticks resting on the bowl"},
     "Close-up photo of a ramen bowl with noodles, a halved soft-boiled egg and wooden chopsticks on the rim.",
     ("egg", "no egg is visible", "Close-up photo of a ramen bowl with noodles and wooden chopsticks on the rim; no egg is visible."),
     ("Oil painting of a quiet river landscape with trees. No food.",
      {"bowl": "none", "egg": "none", "chopsticks": "none"})),
    ("banner", "Red promo banner with the text 'SALE 50% OFF'",
     ["text reads exactly SALE 50% OFF", "red background", "text fully visible"],
     {"text": "reads 'SALE 50% OFF'", "background": "solid red"},
     "Red banner with bold white text reading 'SALE 50% OFF', fully visible.",
     ("text", "reads 'SALE 5% OFF'", "Red banner with bold white text reading 'SALE 5% OFF', fully visible."),
     ("Banner is cropped so the subject is cut off; the lettering is distorted and illegible across the whole width, colours washed out.",
      {"text": "illegible distorted letters", "background": "washed-out pink"})),
    ("anime", "Anime girl with blue hair, one pair of arms, plain background",
     ["one character", "blue hair", "two arms only", "plain background"],
     {"hair": "blue hair", "arms": "two arms", "background": "plain light grey"},
     "Anime girl with blue hair and two arms against a plain light grey background.",
     ("arms", "a third arm emerges from the shoulder", "Anime girl with blue hair, three arms visible, against a plain light grey background."),
     ("Collage of six overlapping characters with merged bodies and duplicated faces on a busy background.",
      {"hair": "mixed colours", "arms": "many overlapping limbs", "background": "busy"})),
    ("interior", "Modern living room with a grey sofa and a potted plant",
     ["modern living room", "grey sofa", "potted plant standing on the floor"],
     {"sofa": "grey sofa", "plant": "potted plant on the floor", "room": "modern bright room"},
     "Bright modern living room with a grey sofa and a potted plant standing on the floor.",
     ("plant", "the plant floats above the floor without a pot", "Bright modern living room with a grey sofa; a plant floats above the floor without a pot."),
     ("Outdoor garden scene with flower beds and a fence. No sofa, no indoor room.",
      {"sofa": "none", "plant": "flowers in beds", "room": "outdoors"})),
    ("card", "Business card: 'Alice Chen', phone 0912-345-678",
     ["name Alice Chen", "phone number 0912-345-678", "clean layout"],
     {"name": "reads 'Alice Chen'", "phone": "reads '0912-345-678'"},
     "Clean business card with the name 'Alice Chen' and the phone number '0912-345-678'.",
     ("phone", "reads '0912-345-67'", "Clean business card with the name 'Alice Chen' and the phone number '0912-345-67'."),
     ("Plain white rectangle with faint grey smudges. No text at all.",
      {"name": "none", "phone": "none"})),
    ("sticker", "Cute robot sticker with a white outline on a transparent background",
     ["cute robot", "white outline", "transparent background", "no watermark"],
     {"robot": "cute round robot", "corner": "clean corner", "outline": "white outline"},
     "Cute round robot sticker with a white outline on a transparent background, no watermark.",
     ("corner", "a faint stock-photo watermark in the lower corner", "Cute round robot sticker with a white outline on a transparent background and a faint stock-photo watermark in the lower corner."),
     ("Black and white pencil sketch of a human hand on paper. No robot.",
      {"robot": "a human hand", "corner": "paper edge", "outline": "none"})),
    ("map", "Treasure map with a dotted path and a red X at the end",
     ["parchment treasure map", "dotted path", "red X at the end of the path"],
     {"path": "dotted path across an island", "x_mark": "red X at the end of the path", "paper": "aged parchment"},
     "Aged parchment treasure map with a dotted path across an island ending at a red X.",
     ("x_mark", "no red X at the end of the path", "Aged parchment treasure map with a dotted path across an island that ends with no red X."),
     ("Satellite photograph of a city grid with roads and buildings. Not a treasure map.",
      {"path": "city roads", "x_mark": "none", "paper": "none"})),
]


def build():
    rows = []
    for i, (name, brief, crit, regs, desc, local, regen) in enumerate(BRIEFS, 1):
        def mk(kind, description, regions, verdict, bad):
            return dict(id=f"I{i:02d}{kind}", brief=brief, criteria=crit, description=description,
                        regions=[{"id": k, "description": v} for k, v in regions.items()], verdict=verdict, bad=bad,
                        global_fault=int(verdict == "regenerate"), group=name)
        rows.append(mk("p", desc, regs, "pass", []))
        rows.append(mk("l", local[2], {**regs, local[0]: local[1]}, "local_edit", [local[0]]))
        rows.append(mk("g", regen[0], regen[1], "regenerate", list(regen[1])))
    return rows


if __name__ == "__main__":
    rows = build()
    out = Path(__file__).with_name("image_dataset.jsonl")
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    import collections
    print(len(rows), "cases", dict(collections.Counter(r["verdict"] for r in rows)), "->", out)
