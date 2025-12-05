# Document Patterns NOW (While Fresh)

## Admin Action Auditing

**Pattern:**
- Import: `from ..services.audit import record_admin_action`
- Usage: after mutation, before `log_json`
- Template:
```python
record_admin_action(
    db,
    admin_user_id=getattr(admin_user, "id", None),
    action="verb_noun",  # e.g. "restore_store"
    target_type="table_name",
    target_id=record.id,
    metadata={"key": "value"},  # optional context
)
```

**Why this helps:**
- Future you can search "admin action pattern"
- Contributors can find examples
- AI can reference your docs

---

## Create Code Templates
```python
# backend/scripts/templates/admin_endpoint.py
"""
Template for admin-only mutation endpoints.
Copy and modify for new admin operations.
"""

@router.post("/{resource_id}/action")
def admin_action_resource(
    resource_id: int,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    # 1. Fetch resource
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(404, detail=f"Resource {resource_id} not found")

    # 2. Perform action
    resource.state = "new_state"
    db.commit()

    # 3. Audit (REQUIRED for admin mutations)
    record_admin_action(
        db,
        admin_user_id=getattr(admin_user, "id", None),
        action="action_resource",
        target_type="resource",
        target_id=resource.id,
        metadata={}
    )

    # 4. Log
    log_json(20, "admin_action_resource", admin_id=admin_user.id, resource_id=resource_id)

    return resource
```

---

## Add Pre-commit Checks
```python
# backend/scripts/check_admin_patterns.py
"""Run before committing admin routes"""

def check_admin_audit_coverage():
    """Every admin mutation should have audit logging"""
    route_files = Path("backend/app/routes").glob("*.py")

    for route_file in route_files:
        content = route_file.read_text()

        # Find admin mutations
        admin_mutations = re.findall(
            r'@router\.(post|put|delete).*\n.*require_admin',
            content
        )

        # For each mutation, check if record_admin_action follows
        for mutation in admin_mutations:
            # Extract function
            func_start = content.find(mutation)
            func_end = content.find("\n@router", func_start + 1)
            func_body = content[func_start:func_end]

            if "record_admin_action" not in func_body:
                print(f"⚠️  Missing audit: {route_file.name}")
```
