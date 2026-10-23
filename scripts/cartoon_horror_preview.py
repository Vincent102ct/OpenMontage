"""Render only the isolated P3.1 synthetic preview through the existing P3 tool route."""
from stickman_horror_preview import main
from tools.character.cartoon_horror_preview import build_preview

if __name__ == "__main__":
    main(project_id="p31-cartoon-horror-preview", builder=build_preview,
         frame_checker="tests/tools/cartoon_horror_frame_checks.cjs",
         qa_timestamps=[0, 1.2, 1.8, 3.2, 152 / 30, 6.4, 8.4, 9.9])
