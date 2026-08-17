---
title: AquaScope Dashboard
emoji: 🌊
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8501
pinned: false
license: mit
short_description: Open-source water data aggregation & analysis toolkit
---

# 🌊 AquaScope Dashboard

Live demo of the [AquaScope](https://github.com/Rekin226/aquascope) open-source
water-data toolkit: 21 live data sources, a hydrology and agricultural-water
lab, extreme-value analysis, and AI-assisted research methodology
recommendations, all in one Streamlit workspace.

- **Source code:** https://github.com/Rekin226/aquascope
- **PyPI:** `pip install "aquascope[dashboard]"`
- **Docs:** https://rekin226.github.io/aquascope/

To update this Space, push a new commit; `requirements.txt` tracks the `main`
branch of the GitHub repository.

## Free AI recommender for visitors

The AI Methodology Recommender works with no credentials at all: it falls back
to a rule-based scorer built into the package. To give visitors the
LLM-enhanced version without asking them for an account, add one free token as
a Space secret:

1. Create a free token at <https://huggingface.co/settings/tokens>
   (read access is enough, no credit card).
2. In the Space, go to **Settings → Variables and secrets → New secret**.
3. Name it `HF_TOKEN` and paste the token.

The dashboard detects it at runtime and offers **✨ Free AI — hosted for this
demo, no key needed** as the default provider. Visitors never see or receive
the token; only the Space's own server uses it.

Optional overrides, set the same way:

| Secret / variable | Default | Purpose |
|---|---|---|
| `HF_TOKEN` | — | Free HuggingFace inference token |
| `AQUASCOPE_LLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Any model served by `router.huggingface.co` |
| `AQUASCOPE_LLM_API_KEY` | — | Use a non-HuggingFace provider instead |
| `AQUASCOPE_LLM_BASE_URL` | — | OpenAI-compatible endpoint for the key above |

The free tier is a shared, rate-limited quota. When it runs out the recommender
shows rule-based results with a notice telling the visitor to add their own key,
so the page never breaks.

The same secrets work on Streamlit Community Cloud, set through
**App settings → Secrets** rather than Space secrets.
