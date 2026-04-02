# Skill: Project Onboarding

## Purpose
Guide CoderX to autonomously "discover" and understand the architecture of a new repository without needing the user to explain it.

## Onboarding Process

### 1. High-level discovery (Snapshot)
- The bot lists the file tree at depth 1-2.
- Identifies "key" files (README.md, package.json, requirements.txt, .env.example, Makefile, docker-compose.yml).

### 2. Architecture analysis using Native Tools
Assign CoderX the following prompt:
```
Explore this repository and analyze:
1. Main tech stack (Language, Frameworks, DB).
2. Project structure (Entry points, routes, logic, models).
3. How to run/test the project.
4. Key coding conventions (Linters, naming styles).

Write a comprehensive summary into `.coderx/onboarding.md`.
```

### 3. Knowledge storage
- The file `.coderx/onboarding.md` will be read by CoderX and injected into the context for all subsequent tasks.

## When to run Onboarding
- When the user sends the `/onboard` command.
- When the bot detects a new workspace that does not yet have a `.coderx/` folder.

## Native Agent Instructions for Onboarding
- Use Shell to `cat` config files.
- Use file tree to crawl folders.
- Use Browser if needed to look up an unfamiliar config/framework found in the project.
- Output must be in English.
