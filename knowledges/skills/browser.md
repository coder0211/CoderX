# Skill: Browser Verification (Playwright)

## Purpose
Use Playwright to visually inspect UI/UX results after writing HTML/CSS/JS.

## Golden Rule
> **Take a screenshot after every CSS/HTML change. If it looks bad → fix it immediately, don't wait.**

---

## Core Tools

```
playwright/navigate   — Open a URL or local file
playwright/screenshot — Capture a screenshot to "see" the interface
playwright/click      — Test interactive elements
playwright/fill       — Test form inputs
playwright/evaluate   — Run JavaScript in the browser context
```

---

## Opening Local Files Correctly

To test an HTML file in the workspace, use the absolute path with the `file://` protocol:

```json
{
  "mcp_tool": "playwright/navigate",
  "mcp_arguments": {
    "url": "file://{workspace}/index.html"
  }
}
```

> ⚠️ Replace `{workspace}` with the absolute path of the current workspace (available in the system prompt).

---

## Visual Verification Process

### 1. After writing HTML/CSS (in VERIFYING state)
```
navigate → screenshot → analyze → fix if needed
```

### 2. Checklist when reviewing a screenshot
- [ ] Is the layout correct? (no broken elements, no overflow)
- [ ] Is text readable? (sufficient contrast, fonts loaded)
- [ ] Spacing appropriate? (not too cramped or too sparse)
- [ ] Responsive? (if needed, test different viewports)
- [ ] Colors harmonious? (not jarring or clashing)

### 3. If the screenshot looks bad
Return to `coding` state:
- Fix CSS immediately — do not leave "ugly but functional" code
- Priority: layout → typography → colors → animations

---

## Testing Interactions

```json
// Click a button
{ "mcp_tool": "playwright/click", "mcp_arguments": { "selector": "#submit-btn" } }

// Fill a form field
{ "mcp_tool": "playwright/fill", "mcp_arguments": { "selector": "#email-input", "value": "test@example.com" } }

// Check for JavaScript console errors
{ "mcp_tool": "playwright/evaluate", "mcp_arguments": { "expression": "window.__errors || []" } }
```

---

## When to use the Browser skill
- ✅ After writing or editing HTML, CSS, or JS
- ✅ When verifying a UI task
- ✅ When testing a user flow (form submit, button click)
- ❌ Not needed for Python/backend-only tasks
