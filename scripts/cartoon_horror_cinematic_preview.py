"""Versioned cinematic revision of P3.1; never writes the original preview project."""
from stickman_horror_preview import main
from tools.character.cartoon_horror_preview import build_cinematic_preview

if __name__ == "__main__":
    main(project_id="p31-cartoon-horror-preview-v2", builder=build_cinematic_preview,
         frame_checker="tests/tools/cartoon_horror_frame_checks.cjs",
         qa_timestamps=[0, 1.8, 3.2, 152/30, 6.4, 7.2, 8.9, 9.9],
         extra_audio=(("door_open", .55),))
