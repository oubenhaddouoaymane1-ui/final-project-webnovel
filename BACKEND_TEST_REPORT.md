# Rendering Backend Redesign — Test Report

**Date**: 2026-07-26
**Test novel**: test_novel.txt (245 words, 2 chapters)
**Pipeline**: Full 7-stage pipeline (Intake → Analysis → Verify → PromptPlan → Render → Assembly → Audit)

---

## Summary

| Metric | Result |
|--------|--------|
| **Pipeline status** | ✅ COMPLETE |
| **Total time** | 1009s (16.8 min) |
| **Images generated** | 7/7 (100%) |
| **Audio generated** | 7/7 (100%) |
| **Video produced** | ✅ 30.3s, 4.6MB |
| **Audit score** | 0.79 / 1.00 |
| **Paid APIs used** | 0 |
| **API keys required** | 0 |
| **Placeholders** | 0 |

---

## Backend Detection Results

### Image Backends (6 registered, 2 healthy)

| Backend | Priority | Status | Notes |
|---------|----------|--------|-------|
| local_gpu | 1 | DOWN | No torch/CUDA on this machine |
| hf_inference | 2 | DOWN | Rate limited / model loading |
| **hf_space** | 3 | **READY** | FLUX.1-schnell via Gradio |
| colab_free | 4 | DOWN | No Colab URL configured |
| kaggle | 5 | DOWN | No Kaggle URL configured |
| **pollinations** | 10 | **READY** | FLUX.1-schnell, no signup |

### TTS Backends (4 registered, 2 healthy)

| Backend | Priority | Status | Notes |
|---------|----------|--------|-------|
| **edge_tts** | 1 | **READY** | Microsoft Edge TTS, neural quality |
| **piper_tts** | 2 | **READY** | Local ONNX TTS |
| hf_tts | 2 | DOWN | Kokoro model unavailable |
| espeak_tts | 99 | DOWN | espeak-ng binary not installed |

---

## Backend Usage During Test

| Asset | Backend Used | Time | Size |
|-------|-------------|------|------|
| ch1_sc1_shot1 | pollinations | 0.8s | 100KB |
| ch1_sc1_shot2 | pollinations | 2.1s | 58KB |
| ch1_sc1_shot3 | pollinations | 1.9s | 76KB |
| ch1_sc1_shot4 | pollinations | 2.0s | 84KB |
| ch2_sc1_shot1 | pollinations | 1.8s | 103KB |
| ch2_sc1_shot2 | pollinations | 1.7s | 99KB |
| ch2_sc1_shot3 | pollinations | 1.5s | 91KB |
| ch1_sc1 narration | edge_tts | 1.0s | 77KB |
| ch2_sc1 narration | edge_tts | 1.8s | 99KB |

---

## Fallback Behavior Verified

1. **HF Space quota exhaustion** → auto-disabled → fell back to Pollinations ✅
2. **Pollinations rate limiting** → cooldown applied → retried successfully ✅
3. **Concurrent request serialization** → 2s interval between Pollinations requests → 0% failure rate ✅

---

## Audit Breakdown

| Check | Score | Status |
|-------|-------|--------|
| Video valid | 1.00 | ✅ |
| Character consistency | 1.00 | ✅ |
| World consistency | 0.17 | ⚠️ (world keywords not in LLM prompts) |
| Scene alignment | 1.00 | ✅ |
| Audio coverage | 1.00 | ✅ |
| Novel fidelity | 0.12 | ⚠️ (narration is summary, not verbatim) |
| **Overall** | **0.79** | **✅ PASS** (threshold: 0.60) |

---

## Architecture

### Priority Order (auto-detected at runtime)

**Images**: Local GPU → HF Inference → HF ZeroGPU Spaces → Colab → Kaggle → Pollinations
**TTS**: Edge TTS → Piper TTS → HF Inference TTS → espeak-ng

### Key Features
- **Zero configuration**: Works out of the box with no API keys
- **Auto-detection**: Health checks run on startup, only healthy backends used
- **Automatic fallback**: Failed backend → next in priority chain
- **Quota awareness**: HF Space quota exhaustion auto-disables backend
- **Rate limiting**: 2s cooldown between Pollinations requests
- **Retry with backoff**: Up to 2 retries per backend per request
- **Graceful degradation**: Pipeline completes even if some backends fail

---

## Known Limitations

1. **Character dedup**: LLM may produce "The King" and "King Theron" as separate entries. Title stripping works for "Sir Aldric" → "Aldric" but not for partial name matches.
2. **World consistency audit**: Checks if world keywords appear in image prompts, but LLM-generated prompts use different phrasing.
3. **Novel fidelity audit**: Compares novel text word overlap with narration summary (expected to be low).
4. **HF Space**: Free ZeroGPU quota is limited (75s/day). Heavy use requires HF token.
5. **CPU-only**: LLM analysis takes ~5 min per 245 words. Full novel (50K words) would take hours.
