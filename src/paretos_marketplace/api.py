"""FastAPI REST endpoints for the Micro-Shift Marketplace."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from paretos_marketplace.atom_generator import generate_atoms, summarise_atoms
from paretos_marketplace.matcher import (
    compose_shift,
    find_eligible_workers,
    validate_claim,
)
from paretos_marketplace.models import Claim, MarketplaceSummary, Worker, WorkAtom
from paretos_marketplace.pricing import price_all_atoms

app = FastAPI(
    title="Paretos Micro-Shift Marketplace",
    description="Decompose staffing plans into claimable 2-hour work atoms",
    version="0.1.0",
)

# ── In-memory state (replaced by DB in production) ──
_atoms: dict[str, WorkAtom] = {}
_workers: dict[str, Worker] = {}
_claims: dict[str, Claim] = {}


# ── Request schemas ──

class GenerateRequest(BaseModel):
    plan: list[dict]


class WorkerCreateRequest(BaseModel):
    name: str
    skills: list[str] = []
    tier: str = "standard"
    productivity_rating: float = 0.7


class ClaimRequest(BaseModel):
    atom_id: str
    worker_id: str


# ── Atom endpoints ──

@app.post("/atoms/generate", summary="Generate atoms from a staffing plan")
def generate(req: GenerateRequest):
    """Generate work atoms from an optimised staffing plan."""
    atoms = generate_atoms(req.plan)
    atoms = price_all_atoms(atoms, list(_workers.values()))

    # Store atoms
    for a in atoms:
        _atoms[a.id] = a

    summary = summarise_atoms(atoms)
    return {"generated": len(atoms), "summary": summary}


@app.get("/atoms", summary="List atoms for a date")
def list_atoms(
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    activity: Optional[str] = Query(None, description="Filter by activity"),
):
    """List work atoms, optionally filtered."""
    atoms = list(_atoms.values())

    if date:
        atoms = [a for a in atoms if str(a.date) == date]
    if status:
        atoms = [a for a in atoms if a.status == status]
    if activity:
        atoms = [a for a in atoms if a.activity.lower() == activity.lower()]

    return {"count": len(atoms), "atoms": atoms}


@app.get("/atoms/{atom_id}", summary="Get atom details")
def get_atom(atom_id: str):
    """Get details for a specific work atom."""
    atom = _atoms.get(atom_id)
    if not atom:
        raise HTTPException(404, f"Atom {atom_id} not found")
    return atom


@app.get("/atoms/{atom_id}/eligible", summary="Eligible workers for an atom")
def eligible_workers(atom_id: str):
    """Find and rank eligible workers for an atom."""
    atom = _atoms.get(atom_id)
    if not atom:
        raise HTTPException(404, f"Atom {atom_id} not found")

    # Build worker-atoms map
    atoms_by_worker: dict[str, list[WorkAtom]] = {}
    for a in _atoms.values():
        for wid in a.claimed_by:
            atoms_by_worker.setdefault(wid, []).append(a)

    day_atoms = [a for a in _atoms.values() if a.date == atom.date]
    eligible = find_eligible_workers(
        atom, list(_workers.values()), atoms_by_worker, day_atoms
    )

    return {
        "atom_id": atom_id,
        "eligible_count": len(eligible),
        "workers": [
            {"worker_id": w.id, "name": w.name, "score": round(s, 3), "tier": w.tier}
            for w, s in eligible
        ],
    }


# ── Claim endpoints ──

@app.post("/claims", summary="Worker claims an atom")
def create_claim(req: ClaimRequest):
    """A worker claims a work atom."""
    atom = _atoms.get(req.atom_id)
    if not atom:
        raise HTTPException(404, f"Atom {req.atom_id} not found")

    worker = _workers.get(req.worker_id)
    if not worker:
        raise HTTPException(404, f"Worker {req.worker_id} not found")

    if atom.remaining_headcount <= 0:
        raise HTTPException(400, f"Atom {req.atom_id} is fully claimed")

    if req.worker_id in atom.claimed_by:
        raise HTTPException(400, f"Worker {req.worker_id} already claimed this atom")

    # Build worker's current atoms
    worker_atoms = [_atoms[aid] for aid in worker.current_atoms if aid in _atoms]
    day_atoms = [a for a in _atoms.values() if a.date == atom.date]

    valid, violations = validate_claim(worker, atom, worker_atoms, day_atoms)
    if not valid:
        raise HTTPException(400, f"Claim violates constraints: {'; '.join(violations)}")

    # Create claim
    claim = Claim(atom_id=req.atom_id, worker_id=req.worker_id, status="confirmed")
    _claims[claim.id] = claim

    # Update atom and worker state
    atom.claimed_by.append(req.worker_id)
    if atom.remaining_headcount <= 0:
        atom.status = "filled"
    else:
        atom.status = "claimed"

    worker.current_atoms.append(req.atom_id)

    return {"claim": claim, "atom_status": atom.status, "remaining": atom.remaining_headcount}


@app.delete("/claims/{claim_id}", summary="Cancel a claim")
def cancel_claim(claim_id: str):
    """Cancel a worker's claim on an atom."""
    claim = _claims.get(claim_id)
    if not claim:
        raise HTTPException(404, f"Claim {claim_id} not found")

    if claim.status == "cancelled":
        raise HTTPException(400, "Claim already cancelled")

    # Undo the claim
    atom = _atoms.get(claim.atom_id)
    worker = _workers.get(claim.worker_id)

    if atom and claim.worker_id in atom.claimed_by:
        atom.claimed_by.remove(claim.worker_id)
        atom.status = "open" if not atom.claimed_by else "claimed"

    if worker and claim.atom_id in worker.current_atoms:
        worker.current_atoms.remove(claim.atom_id)

    claim.status = "cancelled"
    return {"claim": claim}


# ── Worker endpoints ──

@app.post("/workers", summary="Register a worker")
def create_worker(req: WorkerCreateRequest):
    """Register a new worker in the marketplace."""
    worker = Worker(
        name=req.name,
        skills=req.skills,
        tier=req.tier,
        productivity_rating=req.productivity_rating,
    )
    _workers[worker.id] = worker
    return worker


@app.get("/workers", summary="List all workers")
def list_workers():
    return {"count": len(_workers), "workers": list(_workers.values())}


@app.get("/workers/{worker_id}", summary="Get worker details")
def get_worker(worker_id: str):
    worker = _workers.get(worker_id)
    if not worker:
        raise HTTPException(404, f"Worker {worker_id} not found")
    return worker


@app.get("/workers/{worker_id}/shifts", summary="Composed shift for a worker")
def get_worker_shift(worker_id: str, date: str = Query(..., description="Date (YYYY-MM-DD)")):
    """Get the composed shift for a worker on a given date."""
    worker = _workers.get(worker_id)
    if not worker:
        raise HTTPException(404, f"Worker {worker_id} not found")

    from datetime import date as date_type
    target = date_type.fromisoformat(date)
    worker_atoms = [_atoms[aid] for aid in worker.current_atoms if aid in _atoms]

    shift = compose_shift(worker, worker_atoms, target)
    return shift


# ── Dashboard / summary endpoint ──

@app.get("/dashboard/summary", summary="Marketplace summary for a date")
def dashboard_summary(date: Optional[str] = Query(None)):
    """Get fill rates, revenue, and coverage stats."""
    atoms = list(_atoms.values())
    if date:
        atoms = [a for a in atoms if str(a.date) == date]

    if not atoms:
        return {"message": "No atoms found", "atoms": 0}

    total_hc = sum(a.headcount for a in atoms)
    filled_hc = sum(len(a.claimed_by) for a in atoms)
    revenue = sum(a.final_price_eur * len(a.claimed_by) for a in atoms)
    activities: dict[str, int] = {}
    for a in atoms:
        activities[a.activity] = activities.get(a.activity, 0) + 1

    target_date = atoms[0].date if atoms else None

    return MarketplaceSummary(
        date=target_date,
        total_atoms=len(atoms),
        open_atoms=sum(1 for a in atoms if a.status == "open"),
        claimed_atoms=sum(1 for a in atoms if a.status == "claimed"),
        filled_atoms=sum(1 for a in atoms if a.status == "filled"),
        fill_rate_pct=round(filled_hc / max(total_hc, 1) * 100, 1),
        total_headcount_needed=total_hc,
        total_headcount_filled=filled_hc,
        total_revenue_eur=round(revenue, 2),
        activities=activities,
    )


@app.get("/health", summary="Health check")
def health():
    return {
        "status": "ok",
        "atoms": len(_atoms),
        "workers": len(_workers),
        "claims": len(_claims),
    }
