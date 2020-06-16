import serial
import time

# Calculates crc16 (modbus)
def crcCalculator(payload,numBytes):
	crc = 0xFFFF
	byteArray = [(payload>>(8*i))&0xff for i in range(numBytes,-1,-1)]
	for byte in byteArray:
		crc ^= byte
		for i in range(8):
			if((crc & 0x0001) != 0):
				crc >>= 1
				crc ^= 0xA001
			else:
				crc >>= 1
	upperByte = crc & 0x00FF
	lowerByte = (crc & 0xFF00) >> 8
	return (upperByte << 8) | lowerByte

# Constructs the command to send to ATEC
def constructATECCommand(rw,param,data):
	rwDict = {'r':0x03,'w':0x06}
	paramDict = {'PVPVOF':0x1000,'SVSVOF':0x1001,'SV':0x0000,'ENAB':0x0002}
	#Sets ATEC ID to 1 (shouldn't need to be changed)
	idByte = 0x01
	#Gets read/write byte from dict
	rwByte = rwDict[rw]
	#Gets parameter byte from parameter dict
	paramBytes = paramDict[param]
	#Put all that together
	totBytes = (idByte << 8*5) | (rwByte << 8*4) | (paramBytes << 8*2) | data
	#Work out crc byte
	crcBytes = crcCalculator(totBytes,5)
	#Get all 8 bytes to send to ATEC
	totWCrc = (totBytes << 8*2) | crcBytes
	#Return bytes as hex bytestring
	return totWCrc.to_bytes(8,byteorder='big')

#Will build a read command
def readCommand(ATEC,command):
	commandOut = constructATECCommand('r',command,0x0001)
	ATEC.write(commandOut)
	time.sleep(0.2)
	data =  (int.from_bytes(ATEC.readline(),byteorder='big') >> 8*2) & 0xFFFF
	return data

#Wille build a write command
def writeCommand(ATEC,command,data):
	commandOut = constructATECCommand('w',command,data)
	ATEC.write(commandOut)
	time.sleep(0.2)
	#Check the return data is the same as the outgoing, i.e. the write worked
	retData = (int.from_bytes(ATEC.readline(),byteorder='big') >> 8*2) & 0xFFFF
	if(data != retData):
		print('Something Fucked Up')

# Read ATEC temperature
def readTemp(ATEC):
	return float(readCommand(ATEC,'PVPVOF'))/10.0

def readSetPoint(ATEC):
	return float(readCommand(ATEC,'SVSVOF'))/10.0 

# Write ATEC Set point
def writeSetPoint(ATEC,setPoint):
	writeCommand(ATEC,'SV',int(setPoint*10))

# Check if the ATEC PID is working
def readEnableType(ATEC):
	return readCommand(ATEC,'ENAB')

#Set the PID to off
def turnOffPID(ATEC):
	writeCommand(ATEC,'ENAB',0x0000)

#Enable the PID
def turnOnPID(ATEC):
	pass
	#writeCommand(ATEC,'ENAB',0x0004)

#Class to operate on the oven
class oven:
	setPoint = 0.0
	currTemp  = 0.0
	ovenEnabled = False
	port = '/dev/ttyUSB1'
	atec =  serial.Serial(port,baudrate=19200,timeout=0.5)
	def __init__(self):
		self.setPoint = readSetPoint(self.atec)
		self.currTemp = readTemp(self.atec)
		if(readEnableType(self.atec)==4):
			self.ovenEnabled = True
	
	def changeSetPoint(self,setPoint):
		writeSetPoint(self.atec,setPoint)
		self.setPoint = setPoint

	def updateTemp(self):
		self.currTemp = readTemp(self.atec)	
	
	def checkEnabled(self):
		if(readEnableType(self.atec)==4):
			self.ovenEnabled = True
		else:
			self.ovenEnabled = False
	def turnOnPID(self):
		turnOnPID(self.atec)
	def __del__(self):
		self.atec.close()
