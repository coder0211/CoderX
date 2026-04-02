# CoderX Planner — Refine Plan User Message Template
# Used by TaskPlanner.review_and_refine()
# Variables injected at runtime: {project_map}, {latest_result_json}, {next_id}

Current Project Map:
{project_map}

Result of the last completed step:
{latest_result_json}

Based on the current state of the project, update the REMAINING steps of the plan.
Return only a JSON object containing the steps from ID {next_id} onwards.
Adjust, remove, or add steps as needed to best achieve the original goal.
