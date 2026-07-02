"""
Phase 0 — cuOpt / OR-Tools VRP smoke test.

Verifies:
- The VRP solver (cuOpt or OR-Tools fallback) is available
- A tiny 4-location VRP solves and returns a valid route
- Reports which engine was used (cuOpt = GPU, OR-Tools = CPU fallback)
"""

import pytest


class TestCuoptSmoke:
    """Smoke tests for the cuOpt / OR-Tools VRP solver."""

    def test_cuopt_health(self, api_client):
        """GET /cuopt/health reports which solver engine is available."""
        resp = api_client.get("/cuopt/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["engine"] in ("cuopt", "ortools"), (
            f"Unknown engine: {data['engine']}"
        )
        print(f"\n*** VRP solver engine: {data['engine']} ***")
        print(f"*** cuOpt available: {data['cuopt_available']} ***")
        print(f"*** Fallback to OR-Tools: {data['fallback']} ***")

    def test_cuopt_solve_vrp(self, api_client, api_headers):
        """Solve a tiny 4-location, 1-vehicle VRP and verify the route."""
        resp = api_client.get("/cuopt/solve", headers=api_headers, timeout=60.0)
        assert resp.status_code == 200
        data = resp.json()

        # Should have a valid result
        assert data["status"] == "solved", f"VRP not solved: {data}"
        assert "route" in data, "No route in response"
        assert "engine" in data, "No engine reported"

        route = data["route"]
        engine = data["engine"]

        print(f"\n*** VRP engine used: {engine} ***")
        print(f"*** Route: {route} ***")
        if "total_distance" in data:
            print(f"*** Total distance: {data['total_distance']} ***")

        # Basic route validation
        assert len(route) >= 4, f"Route too short: {route}"
        # Route should start and end at depot (0)
        assert route[0] == 0, f"Route doesn't start at depot: {route}"
        assert route[-1] == 0, f"Route doesn't end at depot: {route}"
        # All customers (1, 2, 3) should be visited
        visited = set(route)
        for customer in [1, 2, 3]:
            assert customer in visited, f"Customer {customer} not visited. Route: {route}"

        # Mark which engine ran (for docs/containerization.md)
        if "cuopt" in engine.lower():
            print("\n✅ cuOpt (GPU) VRP solver is working on GB10 arm64!")
        else:
            print("\n⚠️  Fell back to OR-Tools (CPU) VRP solver.")
            if "cuopt_error" in data:
                print(f"   cuOpt error: {data['cuopt_error']}")
