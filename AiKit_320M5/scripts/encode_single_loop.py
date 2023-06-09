# encoding: UTF-8
import platform
# import RPi.GPIO as GPIO
import time

import cv2
import numpy as np
import serial
import serial.tools.list_ports
from pymycobot.mycobot import MyCobot

# y轴偏移量
pump_y = -55
# x轴偏移量
pump_x = 15


class Detect_marker():
    def __init__(self):

        # set cache of real coord
        self.cache_x = self.cache_y = 0

        # get real serial
        self.plist = [
            str(x).split(" - ")[0].strip() for x in serial.tools.list_ports.comports()
        ]

        # Creating a Camera Object
        if platform.system() == "Windows":
            cap_num = 1
            self.cap = cv2.VideoCapture(cap_num, cv2.CAP_DSHOW)
            self.cap.set(3, 640)
            self.cap.set(4, 480)
        elif platform.system() == "Linux":
            cap_num = 0
            self.cap = cv2.VideoCapture(cap_num, cv2.CAP_V4L)
            self.cap.set(3, 640)
            self.cap.set(4, 480)

        # choose place to set cube
        self.color = 0

        # Get ArUco marker dict that can be detected.
        self.aruco_dict = cv2.aruco.Dictionary_get(cv2.aruco.DICT_6X6_250)
        # Get ArUco marker params.
        self.aruco_params = cv2.aruco.DetectorParameters_create()
        # 摄像头的内参矩阵
        self.camera_matrix = np.array([
            [781.33379113, 0., 347.53500524],
            [0., 783.79074192, 246.67627253],
            [0., 0., 1.]])

        # 摄像头的畸变系数
        self.dist_coeffs = np.array(([[3.41360787e-01, -2.52114260e+00, -1.28012469e-03, 6.70503562e-03,
                                       2.57018000e+00]]))

    # 控制吸泵
    def pub_pump(self, flag):
        if flag:
            """start the suction pump"""
            self.mc.set_basic_output(1, 0)
            self.mc.set_basic_output(2, 1)
        else:
            """stop suction pump"""
            self.mc.set_basic_output(1, 1)
            self.mc.set_basic_output(2, 0)
            time.sleep(1)
            self.mc.set_basic_output(2, 1)

    # Grasping motion
    def move(self, x, y, color):
        print(color)

        angles = [
            [0.61, 45.87, -92.37, -41.3, 89.56, 9.58],  # init to point
            [18.8, -7.91, -54.49, -23.02, 89.56, -14.76],
            [17.22, -5.27, -52.47, -25.75, 89.73, -0.26],
        ]

        coords = [
            [145.0, -65.5, 280.1, 178.99, 7.67, -179.9],  # 初始化点 init point
            [253.8, 236.8, 224.6, -170, 6.87, -77.91],  # A分拣区 A sorting area
            [35.9, 235.4, 211.8, -169.33, -9.27, 88.3],  # B分拣区  B sorting area
            [266.5, -219.7, 209.3, -170, -3.64, -94.62],  # C分拣区 C sorting area
            [32, -228.3, 201.6, -168.07, -7.17, -92.56],  # D分拣区 D sorting area

        ]
        print('real_x, real_y:', round(coords[0][0] + x, 2), round(coords[0][1] + y, 2))
        # send coordinates to move mycobot
        self.mc.send_angles(angles[2], 50)
        time.sleep(3)
        self.mc.send_coords([coords[0][0] + x, coords[0][1] + y, 240, 178.99, -3.78, -62.9], 100, 1)
        time.sleep(2)
        self.mc.send_coords([coords[0][0] + x, coords[0][1] + y, 100.5, 178.99, -3.78, -62.9], 100, 1)
        time.sleep(2.5)

        # open pump
        self.pub_pump(True)
        time.sleep(1.5)

        tmp = []
        while True:
            if not tmp:
                tmp = self.mc.get_angles()
            else:
                break
        time.sleep(0.5)

        # print(tmp)
        self.mc.send_angles([tmp[0], -0.71, -54.49, -23.02, 89.56, tmp[5]], 50)
        time.sleep(3)
        # 抓取后放置区域
        self.mc.send_coords(coords[color], 100,
                            1)  # coords[1] 为A分拣区，coords[2] 为B分拣区, coords[3] 为C分拣区，coords[4] 为D分拣区
        time.sleep(6.5)

        # close pump
        self.pub_pump(False)
        time.sleep(6.5)

        self.mc.send_angles(angles[0], 50)
        time.sleep(2)

    # decide whether grab cube
    def decide_move(self, x, y, color):

        # print(x,y)
        # detect the cube status move or run
        if (abs(x - self.cache_x) + abs(y - self.cache_y)) / 2 > 5:  # mm
            self.cache_x, self.cache_y = x, y
            return
        else:
            self.cache_x = self.cache_y = 0
            # 调整吸泵吸取位置，y增大,向左移动;y减小,向右移动;x增大,前方移动;x减小,向后方移动
            self.move(x + 105, y + 140, color)

    # init mycobot
    def init_mycobot(self):
        self.mc = MyCobot(self.plist[0], 115200)
        self.pub_pump(False)
        self.mc.send_angles([0.61, 45.87, -92.37, -41.3, 89.56, 9.58], 50)
        # self.mc.send_coords([135.0, -65.5, 280.1, 178.99, 5.38, -179.9], 20, 1)
        time.sleep(2.5)

    def encode_single(self):
        global pump_y, pump_x
        self.init_mycobot()
        print('ok')
        # control the number of crawls 控制抓取次数
        count = 0

        num = sum_x = sum_y = 0
        while cv2.waitKey(1) < 0:
            success, img = self.cap.read()
            if not success:
                print("It seems that the image cannot be acquired correctly.")
                break

            # transfrom the img to model of gray
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Detect ArUco marker.
            corners, ids, rejectImaPoint = cv2.aruco.detectMarkers(
                gray, self.aruco_dict, parameters=self.aruco_params
            )

            # Determine the placement point of the QR code
            if ids == np.array([[1]]):
                self.color = 1
            elif ids == np.array([[2]]):
                self.color = 2
            elif ids == np.array([[3]]):
                self.color = 3
            elif ids == np.array([[4]]):
                self.color = 4
            if count < 2:
                if len(corners) > 0:
                    if ids is not None:
                        # get informations of aruco
                        ret = cv2.aruco.estimatePoseSingleMarkers(
                            corners, 0.03, self.camera_matrix, self.dist_coeffs
                        )
                        # rvec:rotation offset,tvec:translation deviator
                        (rvec, tvec) = (ret[0], ret[1])
                        (rvec - tvec).any()
                        xyz = tvec[0, 0, :]
                        # calculate the coordinates of the aruco relative to the pump
                        xyz = [round(xyz[0] * 1000 + pump_y, 2), round(xyz[1] * 1000 + pump_x, 2),
                               round(xyz[2] * 1000, 2)]

                        # cv2.putText(img, str(xyz[:2]), (0, 64), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                        for i in range(rvec.shape[0]):
                            # draw the aruco on img
                            cv2.aruco.drawDetectedMarkers(img, corners)

                            if num < 40:
                                sum_x += xyz[1]
                                sum_y += xyz[0]
                                num += 1
                            elif num == 40:
                                self.decide_move(sum_x / 40.0, sum_y / 40.0, self.color)
                                num = sum_x = sum_y = 0
                                count += 1
            else:
                break

            cv2.imshow("encode_image", img)

    def encode_loop(self):
        global pump_y, pump_x
        self.init_mycobot()
        print('ok')
        num = sum_x = sum_y = 0
        while cv2.waitKey(1) < 0:
            success, img = self.cap.read()
            if not success:
                print("It seems that the image cannot be acquired correctly.")
                break

            # transfrom the img to model of gray
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Detect ArUco marker.
            corners, ids, rejectImaPoint = cv2.aruco.detectMarkers(
                gray, self.aruco_dict, parameters=self.aruco_params
            )

            # Determine the placement point of the QR code
            if ids == np.array([[1]]):
                self.color = 1
            elif ids == np.array([[2]]):
                self.color = 2
            elif ids == np.array([[3]]):
                self.color = 3
            elif ids == np.array([[4]]):
                self.color = 4

            if len(corners) > 0:
                if ids is not None:
                    # get informations of aruco
                    ret = cv2.aruco.estimatePoseSingleMarkers(
                        corners, 0.03, self.camera_matrix, self.dist_coeffs
                    )
                    # rvec:rotation offset,tvec:translation deviator
                    (rvec, tvec) = (ret[0], ret[1])
                    (rvec - tvec).any()
                    xyz = tvec[0, 0, :]
                    # calculate the coordinates of the aruco relative to the pump
                    xyz = [round(xyz[0] * 1000 + pump_y, 2), round(xyz[1] * 1000 + pump_x, 2), round(xyz[2] * 1000, 2)]

                    # cv2.putText(img, str(xyz[:2]), (0, 64), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                    for i in range(rvec.shape[0]):
                        # draw the aruco on img
                        cv2.aruco.drawDetectedMarkers(img, corners)

                        if num < 40:
                            sum_x += xyz[1]
                            sum_y += xyz[0]
                            num += 1
                        elif num == 40:
                            self.decide_move(sum_x / 40.0, sum_y / 40.0, self.color)
                            num = sum_x = sum_y = 0

            cv2.imshow("encode_image", img)


if __name__ == "__main__":
    detect = Detect_marker()
    # 提醒用户操作字典
    print("********************************************************")
    print("*  请输入数字选择模式(Please enter number selection mode)：*")
    print("*  1: 单次模式(single mode)                              *")
    print("*  2: 循环模式(loop mode)                                *")
    print("*  3: 退出(quit)                                        *")
    print("********************************************************")
    mode = int(input('请选择模式(please select mode):'))
    if mode == 1:
        detect.encode_single()
    elif mode == 2:
        detect.encode_loop()
    elif mode == 3:
        exit(0)
