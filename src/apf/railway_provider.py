"""Narrow, server-side Railway GraphQL access for one configured environment."""

import os
from uuid import UUID

import httpx

API_URL = "https://backboard.railway.com/graphql/v2"
SCOPE_QUERY = "query { projectToken { projectId environmentId } }"
PROJECT_QUERY = """query ($id: String!) {
  project(id: $id) {
    id name
    services { edges { node { id name } } }
    environments { edges { node { id name } } }
  }
}"""
CREATE_SERVICE = """mutation ($input: ServiceCreateInput!) {
  serviceCreate(input: $input) { id name }
}"""


class RailwayProviderError(RuntimeError):
    """A configured Railway connection is missing, denied, or unverifiable."""


class RailwayClient:
    def __init__(self, token: str, project_id: str, environment_id: str,
                 *, transport: httpx.BaseTransport | None = None):
        self.token = token
        self.project_id = str(UUID(project_id))
        self.environment_id = str(UUID(environment_id))
        self.transport = transport

    @classmethod
    def from_environment(cls) -> "RailwayClient":
        names = ("APF_RAILWAY_PROJECT_TOKEN", "APF_RAILWAY_PROJECT_ID",
                 "APF_RAILWAY_ENVIRONMENT_ID")
        values = [os.environ.get(name, "") for name in names]
        if not all(values):
            raise RailwayProviderError("Railway project connection is not configured")
        try:
            return cls(*values)
        except ValueError:
            raise RailwayProviderError("Railway project connection is invalid") from None

    def _call(self, query: str, variables: dict | None = None) -> dict:
        try:
            with httpx.Client(transport=self.transport, timeout=10.0) as client:
                response = client.post(
                    API_URL,
                    headers={"Project-Access-Token": self.token},
                    json={"query": query, "variables": variables or {}},
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RailwayProviderError("Railway request failed") from error
        if not isinstance(body, dict) or body.get("errors") or not isinstance(body.get("data"), dict):
            raise RailwayProviderError("Railway API returned an error")
        return body["data"]

    def verify_scope(self) -> None:
        scope = self._call(SCOPE_QUERY).get("projectToken")
        if not isinstance(scope, dict) or (scope.get("projectId"), scope.get("environmentId")) != (
            self.project_id, self.environment_id,
        ):
            raise RailwayProviderError("Railway project token scope does not match")

    def snapshot(self) -> dict:
        self.verify_scope()
        project = self._call(PROJECT_QUERY, {"id": self.project_id}).get("project")
        if not isinstance(project, dict) or project.get("id") != self.project_id:
            raise RailwayProviderError("Railway project could not be verified")
        environments = [edge["node"] for edge in project["environments"]["edges"]]
        if self.environment_id not in {item["id"] for item in environments}:
            raise RailwayProviderError("Railway environment could not be verified")
        return {
            "project_id": self.project_id, "environment_id": self.environment_id,
            "project_name": project["name"],
            "services": [edge["node"] for edge in project["services"]["edges"]],
            "source": "RAILWAY_API_LIVE",
        }

    def create_empty_service(self, name: str) -> dict:
        before = self.snapshot()
        if any(item["name"] == name for item in before["services"]):
            raise RailwayProviderError("A service with this name already exists")
        created = self._call(CREATE_SERVICE, {"input": {
            "projectId": self.project_id, "name": name,
        }}).get("serviceCreate")
        if not isinstance(created, dict) or not created.get("id"):
            raise RailwayProviderError("Railway service creation was not confirmed")
        after = self.snapshot()
        if not any(item["id"] == created["id"] and item["name"] == name
                   for item in after["services"]):
            raise RailwayProviderError("Railway accepted creation but read-back is pending")
        return {"id": created["id"], "name": name, "status": "VERIFIED_EMPTY_SERVICE"}
