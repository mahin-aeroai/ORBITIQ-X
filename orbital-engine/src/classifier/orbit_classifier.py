"""
ORBITIQ-X Orbital Engine
Orbit Classifier — LEO/SSO/MEO/GEO/HEO/GTO/VLEO/TLI/DSO
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum

EARTH_MU   = 398600.4418   # km³/s²
EARTH_R    = 6378.137      # km
EARTH_J2   = 1.08262668e-3

class OrbitalRegime(str, Enum):
    VLEO="VLEO"; LEO="LEO"; SSO="SSO"; MEO="MEO"
    GEO="GEO"; GTO="GTO"; HEO="HEO"; TLI="TLI"; DSO="DSO"; UNKNOWN="UNKNOWN"

@dataclass(frozen=True)
class OrbitalElements:
    semi_major_axis_km: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    mean_motion_rev_day: float

    @property
    def perigee_km(self): return self.semi_major_axis_km*(1-self.eccentricity)-EARTH_R
    @property
    def apogee_km(self): return self.semi_major_axis_km*(1+self.eccentricity)-EARTH_R
    @property
    def period_minutes(self): return 1440.0/self.mean_motion_rev_day if self.mean_motion_rev_day>0 else 0.0
    @property
    def mean_altitude_km(self): return self.semi_major_axis_km - EARTH_R

@dataclass(frozen=True)
class ClassificationResult:
    regime: OrbitalRegime
    confidence: float
    sub_type: str | None
    notes: list[str]
    perigee_km: float
    apogee_km: float
    mean_alt_km: float
    period_min: float
    sso_match: bool
    geo_belt: bool

class OrbitClassifier:
    GEO_ALT=35786.0; GEO_TOL=200.0; GEO_INC=2.0; GEO_ECC=0.01
    HEO_ECC=0.25; VLEO_MAX=450.0; LEO_MAX=2000.0

    def classify(self, el: OrbitalElements) -> ClassificationResult:
        p,a,m,t,i,e = el.perigee_km,el.apogee_km,el.mean_altitude_km,el.period_minutes,el.inclination_deg,el.eccentricity
        notes=[]; sub=None; sso=False; geo=False

        if a>300000:
            return ClassificationResult(OrbitalRegime.DSO,0.99,"Deep space",["Apogee > lunar"],p,a,m,t,False,False)
        if a>100000:
            return ClassificationResult(OrbitalRegime.TLI,0.95,None,["Trans-lunar injection"],p,a,m,t,False,False)
        if e>self.HEO_ECC:
            sub="Molniya" if 62<i<65 and 700<t<760 else ("Tundra" if 62<i<65 and 1400<t<1460 else None)
            return ClassificationResult(OrbitalRegime.HEO,0.97,sub,[f"HEO e={e:.3f}"],p,a,m,t,False,False)
        if p<self.LEO_MAX and a>30000 and e>0.5:
            return ClassificationResult(OrbitalRegime.GTO,0.93,None,[f"GTO perigee={p:.0f}km"],p,a,m,t,False,False)
        if abs(m-self.GEO_ALT)<self.GEO_TOL and e<self.GEO_ECC and i<self.GEO_INC:
            return ClassificationResult(OrbitalRegime.GEO,0.98,"Geostationary",[f"GEO belt alt={m:.0f}km"],p,a,m,t,False,True)
        if abs(m-self.GEO_ALT)<500 and e<0.05:
            return ClassificationResult(OrbitalRegime.GEO,0.85,"Near-GEO",[],p,a,m,t,False,False)
        if m>self.LEO_MAX:
            sub="GPS-like" if 55<i<57 and 660<t<690 else None
            return ClassificationResult(OrbitalRegime.MEO,0.95,sub,[f"MEO alt={m:.0f}km"],p,a,m,t,False,False)
        sso=self._is_sso(el)
        if sso:
            return ClassificationResult(OrbitalRegime.SSO,0.97,"Sun-sync LEO",[f"SSO inc={i:.2f}°"],p,a,m,t,True,False)
        if m<self.VLEO_MAX:
            return ClassificationResult(OrbitalRegime.VLEO,0.96,None,[f"VLEO alt={m:.0f}km"],p,a,m,t,False,False)
        return ClassificationResult(OrbitalRegime.LEO,0.95,None,[f"LEO alt={m:.0f}km inc={i:.2f}°"],p,a,m,t,False,False)

    def _is_sso(self, el: OrbitalElements) -> bool:
        a=el.semi_major_axis_km; e=el.eccentricity; inc=math.radians(el.inclination_deg)
        n=math.sqrt(EARTH_MU/a**3)
        prec=math.degrees(-1.5*n*EARTH_J2*(EARTH_R/a)**2*math.cos(inc)/(1-e**2)**2)*86400
        return abs(prec-0.98561)<0.05 and 80<el.inclination_deg<115
