"""SGP4 for near-Earth objects, on the standard library alone: the Vallado
2006 formulation (sgp4init and sgp4) with the WGS-72 constants every TLE is
fitted to. Deep-space objects (a period of 225 minutes or more) are refused;
nothing that passes over visibly to the eye is one. Loaded by path.

The element set comes in as the OMM fields CelesTrak serves as JSON; the
answer is a position in kilometres and a velocity in kilometres a second in
the TEME frame, minutes after the epoch."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

# WGS-72
MU = 398600.8  # km^3/s^2
RADIUS = 6378.135  # km
XKE = 60.0 / math.sqrt(RADIUS**3 / MU)
TUMIN = 1.0 / XKE
J2 = 0.001082616
J3 = -0.00000253881
J4 = -0.00000165597
J3OJ2 = J3 / J2
TWOPI = 2 * math.pi
DEG = math.pi / 180.0
X2O3 = 2.0 / 3.0


class DeepSpace(ValueError):
    pass


@dataclass
class Elements:
    """One object's mean elements at its epoch (angles in radians, mean motion in radians a minute)."""

    norad: int
    name: str
    epoch: datetime
    bstar: float
    inclo: float
    nodeo: float
    ecco: float
    argpo: float
    mo: float
    no_kozai: float

    @classmethod
    def from_omm(cls, d: dict) -> Elements:
        epoch = str(d["EPOCH"])
        when = datetime.fromisoformat(epoch.replace("Z", "")).replace(
            tzinfo=timezone.utc
        )
        return cls(
            norad=int(d["NORAD_CAT_ID"]),
            name=str(d.get("OBJECT_NAME") or d["NORAD_CAT_ID"]).strip(),
            epoch=when,
            bstar=float(d.get("BSTAR") or 0.0),
            inclo=float(d["INCLINATION"]) * DEG,
            nodeo=float(d["RA_OF_ASC_NODE"]) * DEG,
            ecco=float(d["ECCENTRICITY"]),
            argpo=float(d["ARG_OF_PERICENTER"]) * DEG,
            mo=float(d["MEAN_ANOMALY"]) * DEG,
            no_kozai=float(d["MEAN_MOTION"]) * TWOPI / 1440.0,
        )

    @property
    def period_min(self) -> float:
        return TWOPI / self.no_kozai


class Satellite:
    """An element set initialised for propagation; ``at(minutes)`` gives
    (position km, velocity km/s) in TEME."""

    def __init__(self, el: Elements) -> None:
        self.el = el
        self.name, self.norad = el.name, el.norad
        self._init()

    # The initialisation, as sgp4init for the near-earth case
    def _init(self) -> None:
        el = self.el
        ecco, inclo, no_kozai = el.ecco, el.inclo, el.no_kozai
        self.bstar = el.bstar
        eccsq = ecco * ecco
        omeosq = 1.0 - eccsq
        rteosq = math.sqrt(omeosq)
        cosio = math.cos(inclo)
        cosio2 = cosio * cosio
        ak = (XKE / no_kozai) ** X2O3
        d1 = 0.75 * J2 * (3.0 * cosio2 - 1.0) / (rteosq * omeosq)
        delta = d1 / (ak * ak)
        adel = ak * (
            1.0 - delta * delta - delta * (1.0 / 3.0 + 134.0 * delta * delta / 81.0)
        )
        delta = d1 / (adel * adel)
        no_unkozai = no_kozai / (1.0 + delta)
        self.no = no_unkozai
        ao = (XKE / no_unkozai) ** X2O3
        sinio = math.sin(inclo)
        po = ao * omeosq
        con42 = 1.0 - 5.0 * cosio2
        self.con41 = -con42 - cosio2 - cosio2
        posq = po * po
        rp = ao * (1.0 - ecco)
        if TWOPI / no_unkozai >= 225.0:
            raise DeepSpace(
                f"{el.name}: a deep-space object (period {TWOPI / no_unkozai:.0f} min)"
            )
        self.isimp = rp < 220.0 / RADIUS + 1.0
        sfour = 78.0 / RADIUS + 1.0
        qzms2t = ((120.0 - 78.0) / RADIUS) ** 4
        self.x1mth2 = 1.0 - cosio2
        self.x7thm1 = 7.0 * cosio2 - 1.0
        perige = (rp - 1.0) * RADIUS
        if perige < 156.0:
            sfour = perige - 78.0 if perige >= 98.0 else 20.0
            qzms2t = ((120.0 - sfour) / RADIUS) ** 4
            sfour = sfour / RADIUS + 1.0
        pinvsq = 1.0 / posq
        tsi = 1.0 / (ao - sfour)
        self.eta = ao * ecco * tsi
        etasq = self.eta * self.eta
        eeta = ecco * self.eta
        psisq = abs(1.0 - etasq)
        coef = qzms2t * tsi**4
        coef1 = coef / psisq**3.5
        cc2 = (
            coef1
            * no_unkozai
            * (
                ao * (1.0 + 1.5 * etasq + eeta * (4.0 + etasq))
                + 0.375
                * J2
                * tsi
                / psisq
                * self.con41
                * (8.0 + 3.0 * etasq * (8.0 + etasq))
            )
        )
        self.cc1 = self.bstar * cc2
        cc3 = 0.0
        if ecco > 1.0e-4:
            cc3 = -2.0 * coef * tsi * J3OJ2 * no_unkozai * sinio / ecco
        self.x1mth2 = 1.0 - cosio2
        self.cc4 = (
            2.0
            * no_unkozai
            * coef1
            * ao
            * omeosq
            * (
                self.eta * (2.0 + 0.5 * etasq)
                + ecco * (0.5 + 2.0 * etasq)
                - J2
                * tsi
                / (ao * psisq)
                * (
                    -3.0 * self.con41 * (1.0 - 2.0 * eeta + etasq * (1.5 - 0.5 * eeta))
                    + 0.75
                    * self.x1mth2
                    * (2.0 * etasq - eeta * (1.0 + etasq))
                    * math.cos(2.0 * el.argpo)
                )
            )
        )
        self.cc5 = (
            2.0 * coef1 * ao * omeosq * (1.0 + 2.75 * (etasq + eeta) + eeta * etasq)
        )
        cosio4 = cosio2 * cosio2
        temp1 = 1.5 * J2 * pinvsq * no_unkozai
        temp2 = 0.5 * temp1 * J2 * pinvsq
        temp3 = -0.46875 * J4 * pinvsq * pinvsq * no_unkozai
        self.mdot = (
            no_unkozai
            + 0.5 * temp1 * rteosq * self.con41
            + 0.0625 * temp2 * rteosq * (13.0 - 78.0 * cosio2 + 137.0 * cosio4)
        )
        self.argpdot = (
            -0.5 * temp1 * con42
            + 0.0625 * temp2 * (7.0 - 114.0 * cosio2 + 395.0 * cosio4)
            + temp3 * (3.0 - 36.0 * cosio2 + 49.0 * cosio4)
        )
        xhdot1 = -temp1 * cosio
        self.nodedot = (
            xhdot1
            + (0.5 * temp2 * (4.0 - 19.0 * cosio2) + 2.0 * temp3 * (3.0 - 7.0 * cosio2))
            * cosio
        )
        self.omgcof = self.bstar * cc3 * math.cos(el.argpo)
        self.xmcof = 0.0
        if ecco > 1.0e-4:
            self.xmcof = -X2O3 * coef * self.bstar / eeta
        self.nodecf = 3.5 * omeosq * xhdot1 * self.cc1
        self.t2cof = 1.5 * self.cc1
        if abs(cosio + 1.0) > 1.5e-12:
            self.xlcof = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / (1.0 + cosio)
        else:
            self.xlcof = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / 1.5e-12
        self.aycof = -0.5 * J3OJ2 * sinio
        self.delmo = (1.0 + self.eta * math.cos(el.mo)) ** 3
        self.sinmao = math.sin(el.mo)
        if not self.isimp:
            cc1sq = self.cc1 * self.cc1
            self.d2 = 4.0 * ao * tsi * cc1sq
            temp = self.d2 * tsi * self.cc1 / 3.0
            self.d3 = (17.0 * ao + sfour) * temp
            self.d4 = 0.5 * temp * ao * tsi * (221.0 * ao + 31.0 * sfour) * self.cc1
            self.t3cof = self.d2 + 2.0 * cc1sq
            self.t4cof = 0.25 * (
                3.0 * self.d3 + self.cc1 * (12.0 * self.d2 + 10.0 * cc1sq)
            )
            self.t5cof = 0.2 * (
                3.0 * self.d4
                + 12.0 * self.cc1 * self.d3
                + 6.0 * self.d2 * self.d2
                + 15.0 * cc1sq * (2.0 * self.d2 + cc1sq)
            )
        else:
            self.d2 = self.d3 = self.d4 = self.t3cof = self.t4cof = self.t5cof = 0.0
        self.sinio, self.cosio = sinio, cosio

    def at(
        self, tsince: float
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Position (km) and velocity (km/s) in TEME, ``tsince`` minutes after the epoch."""
        el = self.el
        xmdf = el.mo + self.mdot * tsince
        argpdf = el.argpo + self.argpdot * tsince
        nodedf = el.nodeo + self.nodedot * tsince
        argpm = argpdf
        mm = xmdf
        t2 = tsince * tsince
        nodem = nodedf + self.nodecf * t2
        tempa = 1.0 - self.cc1 * tsince
        tempe = self.bstar * self.cc4 * tsince
        templ = self.t2cof * t2
        if not self.isimp:
            delomg = self.omgcof * tsince
            delm = self.xmcof * ((1.0 + self.eta * math.cos(xmdf)) ** 3 - self.delmo)
            temp = delomg + delm
            mm = xmdf + temp
            argpm = argpdf - temp
            t3 = t2 * tsince
            t4 = t3 * tsince
            tempa = tempa - self.d2 * t2 - self.d3 * t3 - self.d4 * t4
            tempe = tempe + self.bstar * self.cc5 * (math.sin(mm) - self.sinmao)
            templ = templ + self.t3cof * t3 + t4 * (self.t4cof + tsince * self.t5cof)
        nm = self.no
        em = el.ecco
        inclm = el.inclo
        am = (XKE / nm) ** X2O3 * tempa * tempa
        nm = XKE / am**1.5
        em = em - tempe
        if em >= 1.0 or em < -0.001:
            raise ValueError(f"{el.name}: the orbit has decayed")
        if em < 1.0e-6:
            em = 1.0e-6
        mm = mm + self.no * templ
        xlm = mm + argpm + nodem
        nodem = math.fmod(nodem, TWOPI)
        argpm = math.fmod(argpm, TWOPI)
        xlm = math.fmod(xlm, TWOPI)
        mm = math.fmod(xlm - argpm - nodem, TWOPI)
        sinim, cosim = math.sin(inclm), math.cos(inclm)
        # long-period periodics
        axnl = em * math.cos(argpm)
        temp = 1.0 / (am * (1.0 - em * em))
        aynl = em * math.sin(argpm) + temp * self.aycof
        xl = mm + argpm + nodem + temp * self.xlcof * axnl
        # Kepler's equation
        u = math.fmod(xl - nodem, TWOPI)
        eo1 = u
        tem5 = 9999.9
        ktr = 1
        sineo1 = coseo1 = 0.0
        while abs(tem5) >= 1.0e-12 and ktr <= 10:
            sineo1, coseo1 = math.sin(eo1), math.cos(eo1)
            tem5 = 1.0 - coseo1 * axnl - sineo1 * aynl
            tem5 = (u - aynl * coseo1 + axnl * sineo1 - eo1) / tem5
            if abs(tem5) >= 0.95:
                tem5 = 0.95 if tem5 > 0.0 else -0.95
            eo1 = eo1 + tem5
            ktr += 1
        # short-period periodics
        ecose = axnl * coseo1 + aynl * sineo1
        esine = axnl * sineo1 - aynl * coseo1
        el2 = axnl * axnl + aynl * aynl
        pl = am * (1.0 - el2)
        if pl < 0.0:
            raise ValueError(f"{el.name}: the orbit has decayed")
        rl = am * (1.0 - ecose)
        rdotl = math.sqrt(am) * esine / rl
        rvdotl = math.sqrt(pl) / rl
        betal = math.sqrt(1.0 - el2)
        temp = esine / (1.0 + betal)
        sinu = am / rl * (sineo1 - aynl - axnl * temp)
        cosu = am / rl * (coseo1 - axnl + aynl * temp)
        su = math.atan2(sinu, cosu)
        sin2u = (cosu + cosu) * sinu
        cos2u = 1.0 - 2.0 * sinu * sinu
        temp = 1.0 / pl
        temp1 = 0.5 * J2 * temp
        temp2 = temp1 * temp
        mrt = (
            rl * (1.0 - 1.5 * temp2 * betal * self.con41)
            + 0.5 * temp1 * self.x1mth2 * cos2u
        )
        su = su - 0.25 * temp2 * self.x7thm1 * sin2u
        xnode = nodem + 1.5 * temp2 * cosim * sin2u
        xinc = inclm + 1.5 * temp2 * cosim * sinim * cos2u
        mvt = rdotl - nm * temp1 * self.x1mth2 * sin2u / XKE
        rvdot = rvdotl + nm * temp1 * (self.x1mth2 * cos2u + 1.5 * self.con41) / XKE
        # orientation vectors
        sinsu, cossu = math.sin(su), math.cos(su)
        snod, cnod = math.sin(xnode), math.cos(xnode)
        sini, cosi = math.sin(xinc), math.cos(xinc)
        xmx = -snod * cosi
        xmy = cnod * cosi
        ux = xmx * sinsu + cnod * cossu
        uy = xmy * sinsu + snod * cossu
        uz = sini * sinsu
        vx = xmx * cossu - cnod * sinsu
        vy = xmy * cossu - snod * sinsu
        vz = sini * cossu
        r = (mrt * ux * RADIUS, mrt * uy * RADIUS, mrt * uz * RADIUS)
        vkmps = RADIUS * XKE / 60.0
        v = (
            (mvt * ux + rvdot * vx) * vkmps,
            (mvt * uy + rvdot * vy) * vkmps,
            (mvt * uz + rvdot * vz) * vkmps,
        )
        return r, v
