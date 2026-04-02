# CoderX Senior Coding Standards

These are mandatory standards for all Developer Agents at CoderX. The goal is to produce high-quality, maintainable code that runs smoothly.

## 1. No Placeholders Policy
- **STRICTLY FORBIDDEN** to use comments like `// logic goes here`, `/* TODO */`, or `# implement later`.
- Every file created or edited must be **COMPLETE** and **IMMEDIATELY RUNNABLE**.
- If a task is too large, break it into modules — but each module must contain its complete logic.

## 2. Architecture & Structure
- **Separation of Concerns**: HTML for structure, CSS for presentation, JS for logic.
- **Variables & Constants**: Use meaningful names, prefer `const` and `let` over `var`.
- **Error Handling**: Use `try-catch` for risky operations (network, file I/O).

## 3. Visual Excellence & UX
CoderX doesn't just code to work — it codes to **look great**. Every web interface must meet:
- **Design Token System**: Use CSS Variables for colors, spacing, and typography to ensure consistency.
- **Modern Layouts**: Always use Flexbox and Grid. Never use float/table for page layout.
- **Premium Typography**: Always integrate Google Fonts (e.g., Inter, Outfit, Roboto). Avoid browser default fonts.
- **Refined Color Palettes**: Use harmonious (HSL-based) color palettes with high contrast and Dark Mode support when needed.
- **Smooth Experience**: Add hover transitions, subtle micro-animations, and reasonable border-radius for a modern feel.
- **Responsive by Default**: The interface must display correctly on all devices (Mobile First approach).
- **No bare HTML**: A senior never writes HTML without accompanying CSS to make it look professional.

## 4. Operational Safety
- **Block hanging commands**: Never run interactive/continuous commands (`npm start`, `watch`) in the shell tool unless there is a background mechanism.
- **Normalize paths**: Always use project-relative paths to avoid "Access Denied" errors.

---
*Any violation of the above standards is considered a Seniority failure.*
