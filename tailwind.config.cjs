// Browser utilities: colors follow the existing data-theme setting.
module.exports = {
  "darkMode": "class",
  "theme": {
    "extend": {
      "colors": {
        "primary": "rgb(var(--stitch-color-primary) / <alpha-value>)",
        "primary-container": "rgb(var(--stitch-color-primary-container) / <alpha-value>)",
        "on-primary": "rgb(var(--stitch-color-on-primary) / <alpha-value>)",
        "on-primary-container": "rgb(var(--stitch-color-on-primary-container) / <alpha-value>)",
        "primary-fixed": "rgb(var(--stitch-color-primary-fixed) / <alpha-value>)",
        "primary-fixed-dim": "rgb(var(--stitch-color-primary-fixed-dim) / <alpha-value>)",
        "secondary": "rgb(var(--stitch-color-secondary) / <alpha-value>)",
        "secondary-container": "rgb(var(--stitch-color-secondary-container) / <alpha-value>)",
        "on-secondary": "rgb(var(--stitch-color-on-secondary) / <alpha-value>)",
        "on-secondary-container": "rgb(var(--stitch-color-on-secondary-container) / <alpha-value>)",
        "secondary-fixed": "rgb(var(--stitch-color-secondary-fixed) / <alpha-value>)",
        "secondary-fixed-dim": "rgb(var(--stitch-color-secondary-fixed-dim) / <alpha-value>)",
        "tertiary": "rgb(var(--stitch-color-tertiary) / <alpha-value>)",
        "tertiary-container": "rgb(var(--stitch-color-tertiary-container) / <alpha-value>)",
        "on-tertiary": "rgb(var(--stitch-color-on-tertiary) / <alpha-value>)",
        "tertiary-fixed": "rgb(var(--stitch-color-tertiary-fixed) / <alpha-value>)",
        "tertiary-fixed-dim": "rgb(var(--stitch-color-tertiary-fixed-dim) / <alpha-value>)",
        "background": "rgb(var(--stitch-color-background) / <alpha-value>)",
        "on-background": "rgb(var(--stitch-color-on-background) / <alpha-value>)",
        "surface": "rgb(var(--stitch-color-surface) / <alpha-value>)",
        "surface-bright": "rgb(var(--stitch-color-surface-bright) / <alpha-value>)",
        "surface-dim": "rgb(var(--stitch-color-surface-dim) / <alpha-value>)",
        "surface-container-lowest": "rgb(var(--stitch-color-surface-container-lowest) / <alpha-value>)",
        "surface-container-low": "rgb(var(--stitch-color-surface-container-low) / <alpha-value>)",
        "surface-container": "rgb(var(--stitch-color-surface-container) / <alpha-value>)",
        "surface-container-high": "rgb(var(--stitch-color-surface-container-high) / <alpha-value>)",
        "surface-container-highest": "rgb(var(--stitch-color-surface-container-highest) / <alpha-value>)",
        "inverse-surface": "rgb(var(--stitch-color-inverse-surface) / <alpha-value>)",
        "inverse-on-surface": "rgb(var(--stitch-color-inverse-on-surface) / <alpha-value>)",
        "inverse-primary": "rgb(var(--stitch-color-inverse-primary) / <alpha-value>)",
        "on-surface": "rgb(var(--stitch-color-on-surface) / <alpha-value>)",
        "on-surface-variant": "rgb(var(--stitch-color-on-surface-variant) / <alpha-value>)",
        "outline": "rgb(var(--stitch-color-outline) / <alpha-value>)",
        "outline-variant": "rgb(var(--stitch-color-outline-variant) / <alpha-value>)",
        "error": "rgb(var(--stitch-color-error) / <alpha-value>)",
        "error-container": "rgb(var(--stitch-color-error-container) / <alpha-value>)"
      },
      "fontFamily": {
        "display-lg": [
          "Plus Jakarta Sans",
          "Inter",
          "sans-serif"
        ],
        "headline-lg": [
          "Plus Jakarta Sans",
          "Inter",
          "sans-serif"
        ],
        "headline-md": [
          "Plus Jakarta Sans",
          "Inter",
          "sans-serif"
        ],
        "headline-sm": [
          "Plus Jakarta Sans",
          "Inter",
          "sans-serif"
        ],
        "body-lg": [
          "Inter",
          "sans-serif"
        ],
        "body-md": [
          "Inter",
          "sans-serif"
        ],
        "body-sm": [
          "Inter",
          "sans-serif"
        ],
        "label-md": [
          "Inter",
          "sans-serif"
        ],
        "label-sm": [
          "Inter",
          "sans-serif"
        ],
        "code-sm": [
          "JetBrains Mono",
          "monospace"
        ]
      },
      "fontSize": {
        "headline-lg": [
          "28px",
          {
            "lineHeight": "36px",
            "letterSpacing": "-0.02em",
            "fontWeight": "700"
          }
        ],
        "headline-md": [
          "20px",
          {
            "lineHeight": "28px",
            "letterSpacing": "-0.01em",
            "fontWeight": "600"
          }
        ],
        "headline-sm": [
          "16px",
          {
            "lineHeight": "24px",
            "fontWeight": "600"
          }
        ],
        "display-lg": [
          "36px",
          {
            "lineHeight": "44px",
            "letterSpacing": "-0.025em",
            "fontWeight": "700"
          }
        ],
        "body-lg": [
          "16px",
          {
            "lineHeight": "26px",
            "fontWeight": "400"
          }
        ],
        "body-md": [
          "14px",
          {
            "lineHeight": "22px",
            "fontWeight": "400"
          }
        ],
        "body-sm": [
          "13px",
          {
            "lineHeight": "18px",
            "fontWeight": "400"
          }
        ],
        "label-md": [
          "12px",
          {
            "lineHeight": "16px",
            "letterSpacing": "0.04em",
            "fontWeight": "600"
          }
        ],
        "label-sm": [
          "11px",
          {
            "lineHeight": "14px",
            "fontWeight": "500"
          }
        ],
        "code-sm": [
          "13px",
          {
            "lineHeight": "20px",
            "fontWeight": "400"
          }
        ]
      }
    }
  },
  "content": [
    "./frontend/index.html",
    "./frontend/js/**/*.js"
  ]
};
