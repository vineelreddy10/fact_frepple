COMPOSE = docker compose -f frepple.compose.yaml

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

pull:
	$(COMPOSE) pull

# The connector reads plan results from frepple's REST input tables. In the
# default web-service mode the plan is held in memory and those tables stay
# empty, so every import silently returns nothing. There is no env var for
# this — it is a row in frepple's `common_parameter` table.
configure-plan:
	$(COMPOSE) exec -T frepple frepplectl shell -c "\
from freppledb.common.models import Parameter; \
p, _ = Parameter.objects.get_or_create(name='plan.webservice'); \
p.value = 'false'; \
p.description = 'Persist plan to DB so the ERPNext connector can read operationplans'; \
p.save(); \
print('plan.webservice =', Parameter.getValue('plan.webservice', 'default', 'true'))"

.PHONY: up down reset logs pull configure-plan
