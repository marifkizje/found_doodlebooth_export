"""
Streamlit questionnaire for the Data Expo avatar card generator.

Run with:

    streamlit run app.py

Requires OPENAI_API_KEY in environment_variables.env for real generation.
Without it, card_pipeline falls back to rule-based name/skill text and the
avatar step will raise a clear error if you try to use it - so for a UI-only
test run, keep an eye on the console output.
"""

from pathlib import Path

import streamlit as st

from card_pipeline import (
    INPUT_FOLDER,
    QuestionnaireAnswers,
    build_card_data,
    compose_card_back,
    compose_card_front,
)
from print_utils import print_card

st.set_page_config(page_title="Data Expo Avatar Card", page_icon="✨", layout="centered")

st.title("✨ Create your Data Avatar Card")
st.caption("Answer a few quick questions and get your own data-themed collectible card.")

LEVEL_OPTIONS = {1: "Data Sprout", 2: "Data Scout", 3: "Insight Hunter", 4: "Data Master", 5: "Data Legend"}
TYPE_OPTIONS = {1: "Steady Shield", 2: "Quality Guardian", 3: "Insight Owl", 4: "Innovox", 5: "AI Sprinter"}
HP_OPTIONS = {1: "Calm Builder", 2: "Steady Planner", 3: "Data Beaver", 4: "Chaos Tamer", 5: "Deadline Dragon"}
ABILITY_OPTIONS = {1: "Sharp Eye", 2: "Bright Spark", 3: "Helping Hand", 4: "Problem Catcher", 5: "Data Whisperer"}
ATTACK1_OPTIONS = {1: "Lightning Start", 2: "Smart Shortcut", 3: "Data Quest", 4: "Clarity Beam", 5: "Insight Wave"}
ATTACK2_OPTIONS = {1: "Brainstorm Cyclone", 2: "Workshop Whirlwind", 3: "Alignment Cannon", 4: "Dataflow Inferno", 5: "Hero Mode"}

with st.form("questionnaire"):
    first_name = st.text_input("First name")

    photo_tab_camera, photo_tab_upload = st.tabs(["📷 Take a photo", "📁 Upload a photo"])
    with photo_tab_camera:
        camera_photo = st.camera_input("Camera")
    with photo_tab_upload:
        uploaded_photo = st.file_uploader("Upload", type=["jpg", "jpeg", "png"])

    st.subheader("A few quick questions")

    evolution = st.select_slider(
        "I consider myself an experienced expert in my field.",
        options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: LEVEL_OPTIONS[v],
    )
    type_ = st.select_slider(
        "I get excited about trying new ideas and technologies.",
        options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: TYPE_OPTIONS[v],
    )
    hp = st.select_slider(
        "Last-minute changes don't easily throw me off balance.",
        options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: HP_OPTIONS[v],
    )
    ability = st.select_slider(
        "I'm often the person colleagues turn to when they're stuck.",
        options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: ABILITY_OPTIONS[v],
    )
    attack1 = st.select_slider(
        "I prefer asking questions before jumping into a solution.",
        options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: ATTACK1_OPTIONS[v],
    )
    attack_text = st.select_slider(
        "I can laugh about the daily chaos of working with data.",
        options=[1, 2, 3, 4, 5], value=3,
    )
    attack2 = st.select_slider(
        "I'd rather solve a problem than spend hours talking about it.",
        options=[1, 2, 3, 4, 5], value=3, format_func=lambda v: ATTACK2_OPTIONS[v],
    )

    use_ai = st.checkbox(
        "Use AI generation (name / avatar / skill text)",
        value=True,
        help="Untick to quickly test the layout using rule-based fallbacks and a placeholder avatar, without calling the OpenAI API.",
    )

    submitted = st.form_submit_button("Generate my card")

if submitted:
    photo_file = camera_photo or uploaded_photo

    if not first_name:
        st.error("Please fill in your first name.")
        st.stop()
    if use_ai and not photo_file:
        st.error("Please take or upload a photo (or untick 'Use AI generation' to test without one).")
        st.stop()

    safe_name = "".join(c for c in first_name if c.isalnum()) or "guest"
    photo_path = INPUT_FOLDER / f"{safe_name}_input.jpg"
    if photo_file is not None:
        with open(photo_path, "wb") as f:
            f.write(photo_file.getbuffer())
    elif not photo_path.exists():
        # No photo and AI generation disabled - drop a placeholder so
        # composition can still run for a layout test.
        from PIL import Image
        Image.new("RGB", (600, 600), "#DDDDDD").save(photo_path)

    answers = QuestionnaireAnswers(
        first_name=first_name,
        photo_path=photo_path,
        evolution=evolution,
        type_=type_,
        hp=hp,
        ability=ability,
        attack1=attack1,
        attack_text=attack_text,
        attack2=attack2,
    )

    with st.spinner("Generating your data avatar card..."):
        card = build_card_data(answers, use_ai=use_ai)
        back_path = compose_card_back(card)
        front_path = compose_card_front(card.rarity)

    st.session_state["card"] = card
    st.session_state["front_path"] = front_path
    st.session_state["back_path"] = back_path

if "card" in st.session_state:
    card = st.session_state["card"]
    front_path = st.session_state["front_path"]
    back_path = st.session_state["back_path"]

    st.success(f"Card {card.card_number} generated — Rarity: {card.rarity}")

    col1, col2 = st.columns(2)
    with col1:
        st.image(str(front_path), caption="Front")
    with col2:
        st.image(str(back_path), caption="Back")

    with st.expander("Card details"):
        st.write(
            {
                "Name": card.pokemon_name,
                "Level": card.level_name,
                "XP": card.xp,
                "Capability": card.capability,
                "Signature skill": card.skill_name,
                "Skill text": card.skill_text,
                "Progress": f"{card.progress_stage}/5 ({card.progress_label})",
                "Rarity": card.rarity,
                "Card number": card.card_number,
            }
        )

    if st.button("🖨️ Print this card"):
        try:
            print_card(str(front_path), str(back_path))
            st.success("Sent to printer!")
        except RuntimeError as e:
            st.error(str(e))
