# "sample009_01.py" 파일 안에 def sum() 가 있다면
# from sample009_01 import sum 
# -> 을 써서 함수 실제코드를 로딩한 후 테스트코드에서 테스트 진행!!!

import unittest
import calendar

# 실제코드
def leap_year(year):
    if year % 400 == 0:
        return True
    elif year % 100 == 0:
        return False
    elif year % 4 == 0:
        return True
    else:
        return False

# 테스트코드
class LeapYearTest(unittest.TestCase):
    def test_leap_year(self):
        self.assertTrue(leap_year(0))
        self.assertFalse(leap_year(1))
        self.assertTrue(leap_year(4))
        self.assertTrue(leap_year(1200))
        self.assertFalse(leap_year(700))

    def test_same_calendar(self):
        #import calendar
        for year in range(0, 100000):
            self.assertEqual(leap_year(year), calendar.isleap(year),
                             f"Year {year} mismatch: {leap_year(year)} vs {calendar.isleap(year)}")

# 테스트를 진행
if __name__ == "__main__":
    unittest.main()