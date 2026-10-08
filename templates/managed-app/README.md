# ARKAON management application kit

Copy `intake.example.json` into a project intake file and replace sample facts with confirmed requirements. Keep assumptions and open questions visible. Copy `connectors.template.json` for each authorized source and leave `enabled=false` until official documentation, owner permission and sandbox tests are complete. Start acceptance checks from `acceptance.template.json`.

Validate and generate a draft plan:

```bash
python src/apf/managed_app_packet.py intake.json --plan-out reports/managed-app-plan.md
```

The validator does not generate provider credentials, activate connectors, change production or approve a deployment.
