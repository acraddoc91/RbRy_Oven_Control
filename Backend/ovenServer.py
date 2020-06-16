from bottle import Bottle,response,request
import oven
import threading
import time
from influxdb import InfluxDBClient
import datetime
from pytz import timezone
import pickle
import logging
import RPi.GPIO as GPIO
import numpy as np

#Alarm class which holds timestamp for alarm
class alarm():
	#Takes in dict/JSON version of alarm and saves alarm parameters
	def __init__(self,alarmDict):
		self.on = alarmDict['on']
		self.recurring = alarmDict['recurring']
		self.minute = alarmDict['minute']
		self.hour = alarmDict['hour']
		self.day = alarmDict['day']
		self.month = alarmDict['month']
		self.year = alarmDict['year']
		self.temperature = alarmDict['temperature']
	#Checks if current time meets the alarm timestamp
	def alarmFired(self):
		fired = False
		if self.on:
			now = datetime.datetime.now(timezone('US/Eastern'))
			if (self.year == now.year or self.year == 0):
				if (self.month == now.month or self.month == 0):
					if (self.day == now.day or self.day == 0):
						if (self.hour == now.hour or self.hour == -1):
							if (self.minute == now.minute or self.minute == -1):
								fired = True
								if not self.recurring:
									self.on = False
									logging.debug(str(self.temperature) + " alarm turned off")
		return fired
	#Exports the alarm parameters to JSON
	def toJson(self):
		return {'temperature':self.temperature,'year':self.year,'month':self.month,'day':self.day,'hour':self.hour,'minute':self.minute,'recurring':self.recurring,'on':self.on}

#This is the bottle server which handles all the http requests
class server(Bottle):
	temperature = 10
	def __init__(self):
		#Create a seperate oven thread which deals with oven interactions
		self.ovenThread = ovenThread()
		#Set up bottle stuff
		super().__init__()
	def start(self):
		#Start oven thread
		self.ovenThread.start()
		self.run(host = '0.0.0.0', port=8080,debug=True,server='cherrypy')
	#Dictates what functions are called for a given endpoint
	def setupRoutes(self):
		self.route('/temperature','GET',self.getTemp)
		self.route('/setPoint','POST',self.changeSetPoint)
		self.route('/setPoint','GET',self.getSetPoint)
		self.route('/setPoint','OPTIONS',self.setPointOptions)
		self.route('/alarms','GET',self.getAlarmList)
		self.route('/alarms','POST',self.setAlarmList)
		self.route('/alarms','OPTIONS',self.alarmListOptions)
		self.route('/PID','GET',self.getPIDStatus)
		#Needed for cross server requests
		self.add_hook('after_request',self.enable_cors)
	def getTemp(self):
		return str(self.ovenThread.getOvenTemp())
	def getSetPoint(self):
		return str(self.ovenThread.getSetPoint())
	#Needed to allow javascript to POST to setPoint
	def setPointOptions(self):
		return 0
	def changeSetPoint(self):
		spPayload = request.json
		print(spPayload['key'] == '105457Js')
		print(spPayload['setPoint'])
		if(str(spPayload['key']) == '105457Js'):
			return str(self.ovenThread.writeSetPoint(float(spPayload['setPoint'])))
		else:
			return 'Incorrect Key'
	def getAlarmList(self):
		alarmList = self.ovenThread.getAlarmList()
		jsonAlarmList = [None]*len(alarmList)
		for i in range(len(alarmList)):
			jsonAlarmList[i] = alarmList[i].toJson()
		response.content_type = 'application/json'
		return {'alarms':jsonAlarmList}
	def setAlarmList(self):
		alarmPayload = request.json
		print(alarmPayload['alarms'])
		if(str(alarmPayload['key']) == '105457Js'):
			alarmList = []
			for i in range (len(alarmPayload['alarms'])):
				try:
					alarmList.append(alarm(alarmPayload['alarms'][i]))
				except:
					logging.warning("Crap alarm")
					pass
			for j in range(len(alarmList)):
				print(alarmList[j].toJson())
			self.ovenThread.setAlarmList(alarmList)
			logging.info("Alarm set")
		else:
			return 'Incorrect Key'
	#Needed to allow javascript to POST to alarms
	def alarmListOptions(self):
		return 0
	def getPIDStatus(self):
		return str(self.ovenThread.getPIDStatus())	
	#Allows cross server requests
	#@hook('after_request')
	def enable_cors(self):
		response.headers['Access-Control-Allow-Origin'] = '*'
		response.headers['Access-Control-Allow-Methods'] = 'PUT, GET, POST, DELETE, OPTIONS'
		response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token,content-type'

class oven_PI:
    def __init__(self,P,I,I_time,set_point):
        self.set_point = set_point
        self.P = P
        self.I = I
        self.int_array = np.ones(I_time)*set_point
        self.on = False
    def update_PI(self,plant_val):
        self.int_array = np.roll(self.int_array,1)
        self.int_array[0] = plant_val
        if(self.P * (plant_val-self.set_point) + self.I * np.sum(self.int_array-self.set_point) < 0):
            self.on = True
        else:
            self.on = False
    def change_set_point(self,set_point):
        self.set_point = set_point
        self.int_array = np.ones(self.int_array.shape)*set_point

#Oven class/thread which does all the oven interactions
class ovenThread(threading.Thread):
	def __init__(self):
		super().__init__()
		self.ovenObj = oven.oven()
		self.running = True
		self.alarmFile = '/home/pi/OvenCntrl/alarms.list'
		try:
			self.alarmList = pickle.load(open(self.alarmFile,'rb'))
		except:
			self.alarmList = []
		self.GPIOPIN = 21
		GPIO.setmode(GPIO.BCM)
		GPIO.setup(self.GPIOPIN,GPIO.OUT)
		self.oven_PI = oven_PI(0,1,5,20)
		#self.oven_PI = oven_PI(0,1,15,20)
	def run(self):
		j = 0
		while self.running:
			self.ovenObj.updateTemp()
			#Check if any alarms have fired every 30s (to make sure alarm definitely fires) as 60s could skip
			if((j%3)==0):
				logging.debug("Checking alarms")
				for i in range(len(self.alarmList)):
					if self.alarmList[i].alarmFired():
						logging.info("Alarm " +str (i) + " fired")
						self.writeSetPoint(self.alarmList[i].temperature)
			#Send the temperature to influx and check if the oven is on every 60s
			if ((j%6) == 0):
				self.tempToInflux()
				self.checkEnabled()
				self.oven_PI.update_PI(self.ovenObj.currTemp)
				if(not self.ovenObj.ovenEnabled):
					self.turnOnOven()
				if(self.oven_PI.on):
					GPIO.output(self.GPIOPIN,1)
				else:
					GPIO.output(self.GPIOPIN,0)
				j = 1
			else:
				j += 1
			time.sleep(10)
	def getOvenTemp(self):
		return (self.ovenObj.currTemp)
	def checkEnabled(self):
		return self.ovenObj.checkEnabled()
	def tempToInflux(self):
		dataOut = []
		dataOut += [{"measurement": "Temperature","tags": {"channel_name": "ovenPV"}, "fields": {"value": self.ovenObj.currTemp}}]
		dataOut += [{"measurement": "Temperature","tags": {"channel_name": "ovenSV"}, "fields": {"value": self.ovenObj.setPoint}}]
		try:
			client = InfluxDBClient('jqi-logger.physics.umd.edu', '8086','rydberg_user','ChooseAbilityPersonMerely','rydberg_db')
			client.write_points(dataOut)
			del client
		except Exception as e:
			print(e)
	def writeSetPoint(self,setPoint):
		self.ovenObj.changeSetPoint(float(setPoint))
		self.oven_PI.change_set_point(float(setPoint))
		logging.info("Set point changed to " + str(setPoint))
		return setPoint
	def getSetPoint(self):
		return self.ovenObj.setPoint
	def setAlarmList(self,alarmListIn):
		self.alarmList = alarmListIn
		pickle.dump(self.alarmList,open(self.alarmFile,'wb'))
		return alarmListIn
	def getAlarmList(self):
		return self.alarmList
	def turnOnOven(self):
		self.ovenObj.turnOnPID()
	def getPIDStatus(self):
		#return self.ovenObj.ovenEnabled
		return self.oven_PI.on

if __name__ ==  "__main__":
	logging.basicConfig(filename="/home/pi/OvenCntrl/ovenServer.log",level=logging.INFO,format='%(asctime)s %(message)s' )
	serv = server()
	serv.setupRoutes()
	serv.start()
