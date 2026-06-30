"""
AI Jumpstart Service — cuOpt / OR-Tools VRP smoke endpoint (Phase 0).

Attempts cuOpt first (GPU VRP); falls back to OR-Tools (CPU VRP) if cuOpt
is not available on this arm64 platform.

Provides:
- GET /cuopt/health  — which solver engine is available
- GET /cuopt/solve   — solve a tiny 4-location VRP and return the route
"""

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Determine which solver is available
# ---------------------------------------------------------------------------
_solver_engine: str | None = None
_cuopt_available: bool = False


def _detect_solver() -> str:
    """Try to import cuopt; fall back to ortools."""
    global _solver_engine, _cuopt_available
    if _solver_engine is not None:
        return _solver_engine

    try:
        import cuopt  # noqa: F401

        _cuopt_available = True
        _solver_engine = "cuopt"
        logger.info("cuOpt detected — using GPU VRP solver")
    except ImportError:
        _cuopt_available = False
        _solver_engine = "ortools"
        logger.warning("cuOpt NOT available on this platform — falling back to OR-Tools (CPU VRP)")

    return _solver_engine


def _solve_vrp_ortools() -> dict:
    """Solve a tiny VRP with OR-Tools (CPU fallback).

    4 locations (0=depot, 1-3 = customers), 1 vehicle.
    Cost matrix:
        0  10  15  20
       10   0  35  25
       15  35   0  30
       20  25  30   0
    """
    from ortools.constraint_solver import routing_enums_pb2, pywrapcp

    # Distance matrix
    distance_matrix = [
        [0, 10, 15, 20],
        [10, 0, 35, 25],
        [15, 35, 0, 30],
        [20, 25, 30, 0],
    ]
    num_locations = len(distance_matrix)
    num_vehicles = 1
    depot = 0

    manager = pywrapcp.RoutingIndexManager(num_locations, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )

    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        return {"error": "No solution found", "engine": "ortools"}

    # Extract route
    route = []
    total_distance = 0
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route.append(node)
        next_index = solution.Value(routing.NextVar(index))
        total_distance += distance_matrix[node][manager.IndexToNode(next_index)]
        index = next_index
    route.append(manager.IndexToNode(index))  # return to depot

    return {
        "engine": "ortools",
        "status": "solved",
        "route": route,
        "total_distance": total_distance,
        "num_locations": num_locations,
        "num_vehicles": num_vehicles,
    }


def _solve_vrp_cuopt() -> dict:
    """Solve a tiny VRP with cuOpt (GPU).

    Same 4-location problem as the OR-Tools version.
    """
    try:
        import cudf
        from cuopt import routing

        cost_matrix = cudf.DataFrame(
            [
                [0.0, 10.0, 15.0, 20.0],
                [10.0, 0.0, 35.0, 25.0],
                [15.0, 35.0, 0.0, 30.0],
                [20.0, 25.0, 30.0, 0.0],
            ],
            dtype="float32",
        )

        n_locations = 4
        n_vehicles = 1
        n_tasks = 3  # locations 1, 2, 3

        dm = routing.DataModel(n_locations, n_vehicles, n_tasks)
        dm.add_cost_matrix(cost_matrix)

        task_locations = cudf.Series([1, 2, 3])
        dm.set_task_locations(task_locations)

        ss = routing.SolverSettings()
        sol = routing.Solve(dm, ss)

        route_df = sol.get_route()
        route = route_df["route"].to_arrow().to_pylist()

        return {
            "engine": "cuopt",
            "status": "solved",
            "route": route,
            "num_locations": n_locations,
            "num_vehicles": n_vehicles,
        }
    except Exception as e:
        logger.error(f"cuOpt solve failed: {e}")
        # Fall back to OR-Tools on any cuOpt runtime error
        logger.info("Falling back to OR-Tools due to cuOpt runtime error")
        result = _solve_vrp_ortools()
        result["cuopt_error"] = str(e)
        result["engine"] = "ortools (cuopt-runtime-fallback)"
        return result


@router.get("/health")
def cuopt_health():
    """Report which VRP solver engine is available."""
    engine = _detect_solver()
    return {
        "status": "ok",
        "engine": engine,
        "cuopt_available": _cuopt_available,
        "fallback": engine == "ortools",
    }


@router.get("/solve")
def cuopt_solve():
    """Solve a tiny 4-location, 1-vehicle VRP as a smoke test."""
    engine = _detect_solver()
    try:
        if engine == "cuopt":
            return _solve_vrp_cuopt()
        else:
            return _solve_vrp_ortools()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VRP solve failed: {e}")
