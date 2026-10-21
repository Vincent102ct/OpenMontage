# Story-to-video test stories

Original short stories written for the M1 acceptance run. Neither was hand-built
before; no code in `tools/story/` or `StoryVideo.tsx` refers to their names, places
or objects (enforced by `tests/tools/test_story_to_video.py`).

- `stories/chiec-o-mau-vang.vi.md` — Vietnamese; office → rainy bus stop → living room;
  two characters, umbrella/bag/letter, a bus, dialogue, a time jump.
- `stories/the-last-loaf.en.md` — English; bakery shop/kitchen/street at night; a child
  character, oven, newspaper, bread hand-over, a coin reveal.

Run (repository root, macOS, Remotion installed):

```sh
.venv/bin/python scripts/story_to_video.py examples/story-to-video/stories/chiec-o-mau-vang.vi.md
```

Feature description: `docs/features/story-to-video-pipeline.md`.
