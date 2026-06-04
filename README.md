# DuoBench Website

Static paper website for DuoBench, designed for GitHub Pages and inspired by the existing `flowtouch.github.io` project while shifting toward a more editorial, blog-like layout.

## Contents

- `index.html`: single-page site
- `static/css/index.css`: custom styling
- `static/js/index.js`: small smooth-scroll helper
- `static/images/`: paper figures and task images
- `static/gifs/`: animated task previews derived from the `media/` clips

## Local preview

Any static file server works. For example:

```bash
cd duobench.github.io
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## GitHub Pages

This repo includes a GitHub Actions workflow at `.github/workflows/deploy-pages.yml`.
Pushes to `main` automatically deploy the site to GitHub Pages.

In the GitHub repository settings, make sure:

- `Pages` is enabled
- `Source` is set to `GitHub Actions`

## Notes

- The page currently uses section-anchor buttons instead of final public paper/code/dataset URLs.
- Those release links can be added directly in `index.html` once the final destinations are ready.
