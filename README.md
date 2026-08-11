# Data Expo Avatar Card

## Files

- `card_pipeline.py` — all the generation logic: rule-based scoring (Level/XP/Capability/Progress), AI name generation, AI avatar generation, AI signature-skill text, rarity draw, and PIL card composition (front + back). **Includes a runnable test block at the bottom.**
- `print_utils.py` — printing logic (adapted from the original script), isolated so the rest of the pipeline can be tested on any machine, not just the Windows laptop with the printer attached.
- `app.py` — the Streamlit questionnaire UI.
- `requirements.txt` — dependencies.
- `environment_variables.env` — put your `OPENAI_API_KEY` here (same as before, not included in this delivery).

## Quick test — no UI, no printer, no API key needed

```bash
pip install -r requirements.txt
python card_pipeline.py
```

This runs the pipeline against a built-in example (`Jasper`) with `TEST_USE_AI = False`, so it:
- skips the OpenAI calls entirely (name and skill text use their rule-based fallbacks),
- creates a plain gray placeholder image to stand in for the avatar,
- still runs the *full* composition logic (scoring, rarity draw, card layout),
- saves `cards/DA-XXX_back.png` and `assets/front_<rarity>.png` so you can open them and check the layout.

Run it a few times to see different rarities and to check the layout doesn't break for longer/shorter names.

To test the real AI pipeline: open `card_pipeline.py`, set `TEST_USE_AI = True`, drop a real photo at `input_images/example_photo.jpg`, and make sure `OPENAI_API_KEY` is set in `environment_variables.env`.

## Full test — with the Streamlit UI

```bash
streamlit run app.py
```

Untick "Use AI generation" in the form to do a layout-only test run without calling the OpenAI API or needing a photo.

## Before the real event

- [ ] Drop real brand fonts into `assets/fonts/` as `brand-bold.ttf` and `brand-regular.ttf` (falls back to a plain default font otherwise — fine for testing, not for print).
- [ ] Replace the placeholder card fronts (`compose_card_front`) with final pre-made brand artwork per rarity tier, saved as `assets/front_common.png`, `assets/front_rare.png`, etc. — the function will automatically use those instead of generating a placeholder once they exist.
- [ ] Confirm the open questions listed in the spec doc (Level/XP mapping, rarity odds, front-card icon & tagline).
- [ ] Test `print_card()` on the actual event printer/laptop — this only works on Windows with `pywin32` installed.
- [ ] Extend the blocked-word safety list in `card_pipeline.py` (`_BLOCKED_SUBSTRINGS`) if needed for your audience/language.
