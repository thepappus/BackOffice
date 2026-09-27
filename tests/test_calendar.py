from __future__ import annotations

from datetime import date, datetime

import pytest

from jpmarket import calendar as jc


class TestHolidays:
    def test_fixed_holidays(self):
        h = jc.holidays(2026)
        assert h[date(2026, 1, 1)] == "New Year's Day"
        assert date(2026, 2, 11) in h
        assert date(2026, 5, 3) in h

    def test_happy_monday_coming_of_age(self):
        # Second Monday of January.
        assert jc.holidays(2026)[date(2026, 1, 12)] == "Coming of Age Day"
        # Before 2000 it was fixed on 15 January.
        assert jc.holidays(1999)[date(1999, 1, 15)] == "Coming of Age Day"

    def test_equinoxes_land_in_plausible_window(self):
        for year in range(1990, 2061):
            vernal = [d for d, n in jc.holidays(year).items() if n == "Vernal Equinox Day"]
            autumnal = [
                d for d, n in jc.holidays(year).items() if n == "Autumnal Equinox Day"
            ]
            assert len(vernal) == 1 and vernal[0].day in (19, 20, 21)
            assert len(autumnal) == 1 and autumnal[0].day in (22, 23, 24)

    def test_substitute_holiday_when_holiday_falls_on_sunday(self):
        # 2027-02-11 is a Thursday; pick a year where a fixed holiday is Sunday.
        # 2024-02-11 (National Foundation Day) was a Sunday -> 12th substitutes.
        h = jc.holidays(2024)
        assert date(2024, 2, 11).weekday() == jc.SUNDAY
        assert h[date(2024, 2, 12)] == "Substitute holiday"

    def test_citizens_holiday_in_silver_week(self):
        # 2026: Respect for the Aged 21 Sep (Mon), Autumnal Equinox 23 Sep (Wed),
        # so 22 Sep becomes a citizens' holiday.
        h = jc.holidays(2026)
        assert h[date(2026, 9, 22)] == "Citizens' holiday"

    def test_2019_imperial_transition_ten_day_golden_week(self):
        closed = [
            date(2019, 4, d) for d in range(27, 31)
        ] + [date(2019, 5, d) for d in range(1, 7)]
        for d in closed:
            assert jc.is_exchange_closed(d), f"{d} should be closed"

    def test_2020_olympic_holiday_moves(self):
        h = jc.holidays(2020)
        assert date(2020, 7, 23) in h  # Marine Day, moved
        assert date(2020, 7, 20) not in h  # would-be third Monday
        assert date(2020, 8, 10) in h  # Mountain Day, moved
        assert date(2020, 8, 11) not in h

    def test_emperors_birthday_moves_with_the_reign(self):
        assert date(2018, 12, 23) in jc.holidays(2018)
        assert date(2020, 2, 23) in jc.holidays(2020)
        # 2019 had neither: the Heisei date ended and the Reiwa date began in 2020.
        h2019 = jc.holidays(2019)
        assert date(2019, 12, 23) not in h2019
        assert date(2019, 2, 23) not in h2019


class TestExchangeClosure:
    def test_year_end_and_new_year(self):
        for d in (date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)):
            assert jc.is_exchange_closed(d)
        assert jc.is_business_day(date(2026, 1, 5))  # Monday

    def test_new_year_days_are_closed_but_not_national_holidays(self):
        # 2 and 3 January are exchange closures, not holidays under the Act.
        assert not jc.is_holiday(date(2026, 1, 2))
        assert jc.is_exchange_closed(date(2026, 1, 2))

    def test_weekends(self):
        assert jc.is_exchange_closed(date(2026, 6, 6))  # Saturday
        assert jc.is_exchange_closed(date(2026, 6, 7))  # Sunday


class TestBusinessDayArithmetic:
    def test_next_and_previous_skip_closures(self):
        friday = date(2026, 6, 5)
        assert jc.next_business_day(friday) == date(2026, 6, 8)
        assert jc.previous_business_day(date(2026, 6, 8)) == friday

    def test_add_business_days(self):
        assert jc.add_business_days(date(2026, 6, 1), 2) == date(2026, 6, 3)
        # T+2 across a weekend.
        assert jc.add_business_days(date(2026, 6, 4), 2) == date(2026, 6, 8)
        assert jc.add_business_days(date(2026, 6, 8), -2) == date(2026, 6, 4)

    def test_add_zero_is_identity_even_on_a_closed_day(self):
        saturday = date(2026, 6, 6)
        assert jc.add_business_days(saturday, 0) == saturday

    def test_business_days_between_is_antisymmetric(self):
        a, b = date(2026, 6, 1), date(2026, 6, 11)
        assert jc.business_days_between(a, b) == -jc.business_days_between(b, a)
        assert jc.business_days_between(a, b) == 8


class TestSessions:
    def test_day_session(self):
        ts = datetime(2026, 6, 1, 10, 30)
        assert jc.classify_session(ts) is jc.Session.DAY
        assert jc.trading_day(ts) == date(2026, 6, 1)

    def test_evening_night_session_belongs_to_next_business_day(self):
        """The rule that gets missed: a Monday-evening trade is Tuesday's."""
        ts = datetime(2026, 6, 1, 20, 0)
        assert jc.classify_session(ts) is jc.Session.NIGHT
        assert jc.trading_day(ts) == date(2026, 6, 2)

    def test_friday_evening_rolls_over_the_weekend(self):
        assert jc.trading_day(datetime(2026, 6, 5, 20, 0)) == date(2026, 6, 8)

    def test_small_hours_belong_to_the_same_calendar_day(self):
        # The session opened the previous evening and is still running.
        assert jc.trading_day(datetime(2026, 6, 2, 3, 0)) == date(2026, 6, 2)

    def test_small_hours_on_a_closed_day_roll_forward(self):
        # Saturday 03:00 — the Friday-evening session; trading day is Monday.
        assert jc.trading_day(datetime(2026, 6, 6, 3, 0)) == date(2026, 6, 8)

    def test_day_session_on_a_closed_day_is_an_error(self):
        with pytest.raises(ValueError, match="not a business day"):
            jc.trading_day(datetime(2026, 6, 6, 10, 0))

    def test_session_boundaries_are_configurable(self):
        """Night session boundaries have moved over time, so they are parameters."""
        late = jc.SessionBoundaries(night_start=jc.time(18, 0))
        ts = datetime(2026, 6, 1, 17, 30)
        assert jc.classify_session(ts) is jc.Session.NIGHT  # default 17:00 start
        assert jc.classify_session(ts, late) is jc.Session.DAY
