# Browser Verification Skill (Playwright)

You have access to a real browser via Playwright. Use this to verify UI/UX and visual quality.

## Core Capabilities
- **Navigation**: `playwright/navigate` to open local HTML files or external URLs.
- **Visuals**: `playwright/screenshot` to "see" what you've built.
- **Interactions**: `playwright/click`, `playwright/fill`, `playwright/type` to test flows.
- **Analysis**: `playwright/inspect_element` to debug layout issues.

## Best Practices for "Premium" UI
1. **Always Screenshot**: After writing CSS/HTML, take a screenshot of the page.
2. **Check Responsiveness**: Use different viewport sizes to ensure the design scales.
3. **Verify Animations**: Observe if transitions are smooth (mentally, by checking if selectors are correct).
4. **Contrast & Type**: Use `screenshot` to verify that text is readable and colors are harmonious.

## Testing Local Files
To test a local file (e.g., `index.html` in your workspace), use the absolute path:
`playwright/navigate({"url": "file:///Users/hoa.nguyen3/Documents/our/CoderX/index.html"})`
(Replace with the actual workspace path).
