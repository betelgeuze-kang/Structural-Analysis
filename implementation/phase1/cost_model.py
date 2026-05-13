#!/usr/bin/env python3
"""
Phase IV-2: Deterministic cost model with Calibration Framework.
실제 시공비 데이터(지역/시점별 단가, 실제 입찰가)를 활용하여 Cost proxy를 캘리브레이션합니다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemberCostInput:
    member_id: str
    member_type: str
    length_m: float
    volume_m3: float
    steel_mass_kg: float
    rebar_ratio: float
    congestion_index: float = 0.0
    lap_splice_ratio: float = 0.0
    anchorage_complexity: float = 0.0
    detailing_violation_ratio: float = 0.0


@dataclass(frozen=True)
class CostBreakdown:
    concrete_cost: float
    steel_cost: float
    rebar_cost: float
    labor_cost: float
    congestion_penalty: float
    lap_splice_penalty: float
    anchorage_penalty: float
    detailing_penalty: float

    @property
    def total_cost(self) -> float:
        return float(
            self.concrete_cost
            + self.steel_cost
            + self.rebar_cost
            + self.labor_cost
            + self.congestion_penalty
            + self.lap_splice_penalty
            + self.anchorage_penalty
            + self.detailing_penalty
        )


@dataclass
class RegionalPriceTable:
    """지역 및 시점에 따른 단가 테이블."""
    region: str = "Standard"
    year: int = 2026
    concrete_per_m3: float = 110.0
    steel_per_kg: float = 1.8
    rebar_per_kg: float = 1.3
    labor_factor: float = 1.0


class CostModelCalibrator:
    """실 단가 및 공사비 데이터를 바탕으로 cost proxy 계수를 자동 보정합니다."""
    
    def __init__(self, price_table: RegionalPriceTable | None = None):
        self.price_table = price_table or RegionalPriceTable()
        # 보정 계수 (Calibration factors)
        self.calib_concrete = 1.0
        self.calib_steel = 1.0
        self.calib_rebar = 1.0
        self.calib_labor = 1.0
        
        self.base_labor_unit = {
            "beam": 10.0,
            "column": 12.0,
            "wall": 14.0,
            "slab": 9.0,
            "foundation": 16.0,
            "connection": 8.0,
        }

    def calibrate_from_actual_data(self, actual_project_costs: list[dict[str, float]], predicted_project_costs: list[dict[str, float]]):
        """실제 공사비와 모델 예측값을 비교하여 보정 계수를 산출합니다."""
        if not actual_project_costs or len(actual_project_costs) != len(predicted_project_costs):
            return
            
        # 단순 평균 비율 기반 보정 (실제/예측)
        sum_actual_conc = sum(p.get("concrete_cost", 0) for p in actual_project_costs)
        sum_pred_conc = sum(p.get("concrete_cost", 0) for p in predicted_project_costs)
        if sum_pred_conc > 0:
            self.calib_concrete = sum_actual_conc / sum_pred_conc
            
        sum_actual_steel = sum(p.get("steel_cost", 0) for p in actual_project_costs)
        sum_pred_steel = sum(p.get("steel_cost", 0) for p in predicted_project_costs)
        if sum_pred_steel > 0:
            self.calib_steel = sum_actual_steel / sum_pred_steel
            
        sum_actual_rebar = sum(p.get("rebar_cost", 0) for p in actual_project_costs)
        sum_pred_rebar = sum(p.get("rebar_cost", 0) for p in predicted_project_costs)
        if sum_pred_rebar > 0:
            self.calib_rebar = sum_actual_rebar / sum_pred_rebar

    def estimate_member_cost(self, member: MemberCostInput) -> CostBreakdown:
        member_type = str(member.member_type).strip().lower()
        
        # 적용 단가 산출
        conc_price = self.price_table.concrete_per_m3 * self.calib_concrete
        steel_price = self.price_table.steel_per_kg * self.calib_steel
        rebar_price = self.price_table.rebar_per_kg * self.calib_rebar
        
        labor_unit = self.base_labor_unit.get(member_type, 10.0) * self.price_table.labor_factor * self.calib_labor
        
        concrete_cost = max(float(member.volume_m3), 0.0) * conc_price
        steel_cost = max(float(member.steel_mass_kg), 0.0) * steel_price
        
        rebar_mass_kg = max(float(member.volume_m3), 0.0) * max(float(member.rebar_ratio), 0.0) * 7850.0
        rebar_cost = rebar_mass_kg * rebar_price
        
        labor_cost = max(float(member.length_m), 0.0) * labor_unit
        
        # Penalties based on complex detailing
        congestion_penalty = rebar_cost * max(float(member.congestion_index), 0.0) * 0.08
        lap_splice_penalty = rebar_cost * max(float(member.lap_splice_ratio), 0.0) * 0.18
        anchorage_penalty = (labor_cost + rebar_cost * 0.15) * max(float(member.anchorage_complexity), 0.0) * 0.35
        detailing_penalty = (rebar_cost + labor_cost) * max(float(member.detailing_violation_ratio), 0.0) * 0.50
        
        return CostBreakdown(
            concrete_cost=float(concrete_cost),
            steel_cost=float(steel_cost),
            rebar_cost=float(rebar_cost),
            labor_cost=float(labor_cost),
            congestion_penalty=float(congestion_penalty),
            lap_splice_penalty=float(lap_splice_penalty),
            anchorage_penalty=float(anchorage_penalty),
            detailing_penalty=float(detailing_penalty),
        )

    def estimate_project_cost(self, members: list[MemberCostInput]) -> dict[str, float]:
        total = concrete = steel = rebar = labor = 0.0
        congestion = lap_splice = anchorage = detailing = 0.0
        
        for member in members:
            b = self.estimate_member_cost(member)
            total += b.total_cost
            concrete += b.concrete_cost
            steel += b.steel_cost
            rebar += b.rebar_cost
            labor += b.labor_cost
            congestion += b.congestion_penalty
            lap_splice += b.lap_splice_penalty
            anchorage += b.anchorage_penalty
            detailing += b.detailing_penalty
            
        return {
            "total_cost": float(total),
            "concrete_cost": float(concrete),
            "steel_cost": float(steel),
            "rebar_cost": float(rebar),
            "labor_cost": float(labor),
            "congestion_penalty": float(congestion),
            "lap_splice_penalty": float(lap_splice),
            "anchorage_penalty": float(anchorage),
            "detailing_penalty": float(detailing),
        }

    def parameter_sensitivity_analysis(self, members: list[MemberCostInput]) -> dict[str, dict[str, float]]:
        """단가 변동(±10%) 시 총 공사비의 민감도(%) 분석을 수행합니다."""
        base_cost = self.estimate_project_cost(members)["total_cost"]
        if base_cost == 0:
            return {}
            
        results = {}
        original_table = RegionalPriceTable(
            region=self.price_table.region,
            year=self.price_table.year,
            concrete_per_m3=self.price_table.concrete_per_m3,
            steel_per_kg=self.price_table.steel_per_kg,
            rebar_per_kg=self.price_table.rebar_per_kg,
            labor_factor=self.price_table.labor_factor
        )
        
        params = ["concrete_per_m3", "steel_per_kg", "rebar_per_kg", "labor_factor"]
        
        for param in params:
            res = {}
            for pct_change in [-0.10, +0.10]:
                val = getattr(original_table, param)
                setattr(self.price_table, param, val * (1.0 + pct_change))
                new_cost = self.estimate_project_cost(members)["total_cost"]
                res[f"{pct_change*100:+.0f}%"] = round(((new_cost - base_cost) / base_cost) * 100.0, 2)
                # Restore
                setattr(self.price_table, param, val)
            results[param] = res
            
        return results

# Legacy wrappers for backward compatibility
_default_calibrator = CostModelCalibrator()

def estimate_member_cost(member: MemberCostInput) -> CostBreakdown:
    return _default_calibrator.estimate_member_cost(member)

def estimate_project_cost(members: list[MemberCostInput]) -> dict[str, float]:
    return _default_calibrator.estimate_project_cost(members)


__all__ = [
    "CostBreakdown",
    "MemberCostInput",
    "RegionalPriceTable",
    "CostModelCalibrator",
    "estimate_member_cost",
    "estimate_project_cost",
]
