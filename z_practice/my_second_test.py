# "sample009_01.py" 파일 안에 def sum() 가 있다면
# from sample009_01 import sum 
# -> 을 써서 함수 실제코드를 로딩한 후 테스트코드에서 테스트 진행!!!

import unittest
import requests
import json


# 실제코드
class TddExercise():
    def __init__(self):
        self.to = "2020-02-25"
        self.count = 100
        self.URL = "https://api.upbit.com/v1/candles/minutes/1"
        self.data = []

    def set_period(self, to, count):
        self.to = to
        self.count = count

    def initialize_from_server(self):
        """ 서버에서 데이터를 받아와서 self.data에 저장하는 메소드 """
        query_string = {"market": "KRW-BTC", "to": self.to, "count": self.count}

        response = requests.get(self.URL, params=query_string)
        self.data = response.json()
        print(len(self.data))
        #print(self.data[0])

# 테스트코드
class TddExerciseTests(unittest.TestCase):
    
    def test_set_period_update_period_correctly(self):
        ex = TddExercise()
        self.assertEqual(ex.to, "2020-02-25")
        self.assertEqual(ex.count, 100)

        ex.set_period("2020-02-25T06:41:00Z", 10)

        self.assertEqual(ex.to, "2020-02-25T06:41:00Z")
        self.assertEqual(ex.count, 10)

    def test_initialize_from_server_update_data_correctly_example(self):
        ex = TddExercise()
        self.assertEqual(len(ex.data), 0)

        ex.initialize_from_server()

        self.assertEqual(len(ex.data), 100)

# 테스트를 진행
if __name__ == "__main__":
    unittest.main()