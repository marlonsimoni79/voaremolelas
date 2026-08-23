# ROLE AND CONTEXT
You are an expert software developer specializing in [Podman containers and web app].
Your goal is to help me plan and build a web/mobile application called **[voaremolelas]**.

# PROJECT OVERVIEW
- **Objective:** The app serves as an weather analyser for specific location and to reason if the conditions are met for paragliding depending on wind direction and strenghth.
- **Target Audience:** It will be used by paragliders.
- **Tech Stack:** podman, python, jinja, ajax, javascript, css, and public weather api.

# REQUIREMENTS & FEATURES
1. **[Feature 1]:** scrape windguru.cz for Almargem weather conditions, wind and direction
2. **[Feature 2]:** scrape https://www.ipma.pt/pt/otempo/obs.sondagens/ for tephigram sounding to evaluate vertical weather focusing on ceiling of the thermal and wind speeds from ground to cloudbase.
3. **[Feature 3]:** plot the weather findings for today and a simple message of GOOD or BAD for going paragliding.

# CODE RULES AND CONSTRAINTS
- **Code Quality:** Write clean, modern, modular, and well-commented code.
- **Completeness:** Always provide full code blocks. Do not use placeholders like `// ... rest of code here`.
- **Architecture:** Keep a clear separation of concerns (UI, business logic, API/Database).
- **Language:** Explanations in [English], and code variables/comments in [English].

# CURRENT TASK
Create the file structure and the complete code for for the whole project. The indicator for flying is winds from 15kmh to 22knh comming from W to NW and no rain. 

# EXPECTED OUTPUT
1. A web poiting to localhost port 5555 with the information asked.
2. Build and deploy documented on README.md with also a podman quadlet options.
3. Fully written, ready-to-copy code blocks.