import configparser
import requests
from datetime import date,datetime,timedelta
import json
import os
import fnmatch
from requests.exceptions import HTTPError
from os import listdir
from os.path import isfile, join
from LateObject import LateObject
from TrainLine import JsonArgs
import sys

DATE_FORMAT = "%Y-%m-%d"
OUTBOUND_ATTRIBUTE_MESSAGE_DIR = os.getcwd() + '/downloaded/outbound/sao'
INBOUND_ATTRIBUTE_MESSAGE_DIR = os.getcwd() + '/downloaded/inbound/sao'
OUTBOUND_SERVICE_MESSAGE_DIR = os.getcwd() + '/downloaded/outbound/saopid'
INBOUND_SERVICE_MESSAGE_DIR = os.getcwd() + '/downloaded/inbound/saopid'
OUTBOUND_ATTRIBUTE_MESSAGE = OUTBOUND_ATTRIBUTE_MESSAGE_DIR +'/serviceAttributesOutbound'
INBOUND_ATTRIBUTE_MESSAGE = INBOUND_ATTRIBUTE_MESSAGE_DIR +'/serviceAttributesInbound'
OUTBOUND_SERVICE_MESSAGE = OUTBOUND_SERVICE_MESSAGE_DIR +'/serviceAttributesOutboundTestdata'
INBOUND_SERVICE_MESSAGE = INBOUND_SERVICE_MESSAGE_DIR + '/serviceAttributesInboundTestdata'
LOCATION = 'location'
LOCATIONS = 'locations'
GBTT_PTD = 'gbtt_ptd'
GBTT_PTA = 'gbtt_pta'
ACTUAL_TD = 'actual_td'
ACTUAL_TA = 'actual_ta'
LATE_CANC_REASON = 'late_canc_reason'
DATE_OF_SERVICE = 'date_of_service'
SERVICE_ATTRIBUTES_DETAILS = 'serviceAttributesDetails'
DEPARTURE_STATION = 'departureStation'
INBOUND_JOURNEY = 'INBOUND_JOURNEY'
OUTBOUND_JOURNEY = 'OUTBOUND_JOURNEY'
START_DATE_STRING = 'START_DATE'
DAYS_BACK_STRING = 'DAYS+BACK'
FILE_LOCATION_STRING = 'FILE_LOCATION_STRING'
DIR_LOCATION_STRING = 'DIR_LOCATION_STRING'
START_LOCATION_STRING = 'START_LOCATION'
TO_LOCATION_STRING = 'TO_LOCATION'
START_TIME = 'START_TIME'
END_TIME = 'END_TIME'
RESULT_FILE_STRING = 'LATE_TRAIN_STRING'


def writeServiceMetricsTestData(from_station, to_station,from_time, to_time, to_date,days_difference, fileName):
    #seems like there might be a limit to the amount of daa being returned.
    #need to pull in a loop.....
    for counter in range(0, days_difference):
        d = (to_date - timedelta(days=counter)).strftime(DATE_FORMAT)
        print ("getting all data for date - " + str(d))
        fname = fileName + str(d) + ".json"
        if not os.path.isfile(fname):
            try:
                creds = getCredentials('/Users/simonwilliams/Documents/trainApp/trainConfig.txt')
                response = requests.post('https://hsp-prod.rockshore.net/api/v1/serviceMetrics',
                                         auth=(creds[0],creds[1]),
                                         json={'from_loc':from_station,'to_loc':to_station,'from_time':from_time,'to_time':to_time,
                                               'from_date':d,'to_date':d,'days':'WEEKDAY'})

                response.raise_for_status()
            except HTTPError as http_err:
                print(f'HTTP error occured:{http_err}')
                print(f'HTTP error occurred: {http_err}')
                continue
            except Exception as err:
                print(f'Other error occurred: {err}')
                continue
            writeFile(fname,json.dumps(response.json()))

def writeFile(fileName,data):

    f = open(fileName, "w+")
    f.write(data)
    f.close()

def writeAttributeMessageTestData(pidList,fileName):

    for pid in pidList:
        fname = fileName + pid + ".json"
        if not os.path.isfile(fname):
            try:
                creds = getCredentials('/Users/simonwilliams/Documents/trainApp/trainConfig.txt')
                response = requests.post('https://hsp-prod.rockshore.net/api/v1/serviceDetails',
                                         auth=(creds[0],creds[1]),
                                         json={'rid':pid})
                response.raise_for_status()
            except HTTPError as http_err:
                print(f'HTTP error occured:{http_err}')
                print(f'HTTP error occurred: {http_err}')
            except Exception as err:
                print(f'Other error occurred: {err}')
            writeFile(fname, json.dumps(response.json()))

def generatePidList(dir):
    ridList = []
    files = [f for f in listdir(dir) if isfile(join(dir, f))]
    for fileName in files:
        for key in readjson(dir + '/' + fileName)["Services"]:
            if "serviceAttributesMetrics" in key:
                ridsDict = key["serviceAttributesMetrics"]
                if "rids" in ridsDict:
                    rList = ridsDict["rids"]
                    if(len(rList)>0):
                        ridList.append(rList[0])
    return ridList

def getCredentials(credentialsFile):

    config = configparser.ConfigParser()
    config.read(credentialsFile)
    username = config.get("configuration","username")
    password = config.get("configuration","password")
    return [username,password]

def readjson(fileName):
    if os.path.exists(fileName):
        with open(fileName) as json_file:
            data = json.load(json_file)
        return data
    return None

def generateAttrbuteDictionary(directory):
        jsonlist = []
        fileNameList = [f for f in listdir(directory) if isfile(join(directory, f))]
        for name in fileNameList:
            jsonlist.append(readjson(directory + '/' +name))
        return jsonlist

def generateLateTrainObject(departureLocation, arrivalLocation, serviceAttribute):
    locationsList = serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][LOCATIONS]
    lateObjectArray = []
    for item in locationsList:
        #turns out the late reason is not actually always applied.
        if departureLocation in item[LOCATION] or arrivalLocation in item[LOCATION]:
            lateObjectInstance = LateObject()
            lateObjectInstance.actual_ta = item[ACTUAL_TA]
            lateObjectInstance.actual_td = item[ACTUAL_TD]
            lateObjectInstance.gbtt_pta =item[GBTT_PTA]
            lateObjectInstance.gbtt_ptd =item[GBTT_PTD]
            lateObjectInstance.late_canc_reason =item[LATE_CANC_REASON]
            lateObjectInstance.location=item[LOCATION]
            lateObjectInstance.date_of_service=serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]
            lateObjectInstance.departureStation= (departureLocation == item[LOCATION])
            if item[ACTUAL_TA] != '' and item[GBTT_PTA] != '':
                lateObjectInstance.delay_time = LateObject.calculate_delay(item[ACTUAL_TA],item[GBTT_PTA])
            else: lateObjectInstance.delay_time = 0
            if lateObjectInstance.delay_time > 1:
                lateObjectArray.append(lateObjectInstance)
    return lateObjectArray

def filesInDir(dir,filename):
    counter = 0
    for file in os.listdir(dir):
        if fnmatch.fnmatch(file, filename +'*'):
            counter +=1
    return counter

#this does where the latest object when the endpoint is the last station.
def getLatestTrainObject(listOfTrainObjects):
    returnTrainObjectList = {}
    for dayList in listOfTrainObjects.values():
        for timeList in dayList:
            #set the arrival and departure for the day
            if len(timeList) ==2:
                currentDeparture = timeList[0]
                currentArrival = timeList[1]
                if currentArrival.date_of_service not in returnTrainObjectList:
                    returnTrainObjectList[currentArrival.date_of_service] = [currentDeparture,currentArrival]
                    continue
            else: continue
            #now to compare the lateness with the current latest train.
            for trainArray in returnTrainObjectList.values():
                trainObjectArrival = trainArray[1]
                if int(trainObjectArrival.delay_time) < int(currentArrival.delay_time):
                    returnTrainObjectList[currentArrival.date_of_service] = [currentDeparture,currentArrival]
    return returnTrainObjectList

def writeLateTrainsToFile(fileName,trainObjectList, arrival):
    #need to update the writer for specifc outbound journeys.
    #latestTrainList = list(trainObjectList.keys())
    #latestTrainList.sort()
    output = 'Outbound Train To ' + arrival + '\n'
    output = output + 'Date, Departure Time, Delay Time' + '\n'
    for key in sorted(trainObjectList.keys()):
        vars = trainObjectList[key]
        departTrain = trainObjectList[key][0] if trainObjectList[key][0].departureStation == True else trainObjectList[key][1]
        arrivalTrain = trainObjectList[key][0] if trainObjectList[key][0].departureStation == False else trainObjectList[key][1]
        if departTrain.date_of_service != None:
            output =  output + str(departTrain.date_of_service) + ','+ str(departTrain.gbtt_ptd) +',' + str(arrivalTrain.delay_time) + '\n'

    writeFile(os.getcwd() +'/Results/'+ fileName+'.csv',output)

def trimToRouteOnlyDictionary(listOfAllTrainTimes, departureStation, arrivalLocation):
    lateTrainDictionary = {}
    for serviceAttribute in listOfAllTrainTimes:
        if serviceAttribute != None and SERVICE_ATTRIBUTES_DETAILS in serviceAttribute and DATE_OF_SERVICE in serviceAttribute[SERVICE_ATTRIBUTES_DETAILS] and LOCATIONS in serviceAttribute[SERVICE_ATTRIBUTES_DETAILS]:
            lateTrainArray = generateLateTrainObject(departureStation,arrivalLocation,serviceAttribute)
            if len(lateTrainArray) == 2 and lateTrainArray[0] != None and lateTrainArray[1] != None:
                dateOfService = lateTrainArray[0].date_of_service
                if dateOfService in lateTrainDictionary:
                    ltl = lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]]
                    ltl.append(lateTrainArray)
                    lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]] = ltl
                else:
                    lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]] = [lateTrainArray]
    return lateTrainDictionary

def newMain(serviceDetailsMap):
    for key, value in serviceDetailsMap.items():
        writeServiceMetricsTestData(value[DEPARTURE_STATION],value[TO_LOCATION_STRING],value[START_TIME],
                                    value[END_TIME],value[START_DATE_STRING], value[DAYS_BACK_STRING], value[FILE_LOCATION_STRING])
        writeAttributeMessageTestData(generatePidList(value[DIR_LOCATION_STRING]),OUTBOUND_SERVICE_MESSAGE)
        listOfAllTrainTimes = generateAttrbuteDictionary(OUTBOUND_SERVICE_MESSAGE_DIR)
        #create a map of the to and from stations to compare.
        routeDictionary = trimToRouteOnlyDictionary(listOfAllTrainTimes,value[DEPARTURE_STATION],value[TO_LOCATION_STRING])
        latestTrainDictonary = getLatestTrainObject(routeDictionary)
        writeLateTrainsToFile(value[RESULT_FILE_STRING],latestTrainDictonary,value[TO_LOCATION_STRING])
        print('Completed ' + value[RESULT_FILE_STRING])

if __name__== "__main__":
    serviceDetailsMap = JsonArgs.getJson(sys.argv)
    newMain(serviceDetailsMap)
    print('All complete')

'''def getSecondaryTrainObject(list_of_train_objects):
    #iterate though and pull out the tuple with the biggest delay time
    delay_time = 0
    listlocation = 0
    for index, item in enumerate(list_of_train_objects):
        for t in item:
            if t.delay_time > delay_time:
                delay_time = t.delay_time
                listlocation = index

    return list_of_train_objects[listlocation]'''

'''def generateLateTrainDictionary(location, date_of_service):
    locationsList = serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][LOCATIONS]
    lateDictionary={}
    for item in locationsList:
        #turns out the late reason is not actually always applied.
        if location in item[LOCATION]:
            lateObjectInstance = LateObject()
            lateObjectInstance.actual_ta = item[ACTUAL_TA]
            lateObjectInstance.actual_td = item[ACTUAL_TD]
            lateObjectInstance.gbtt_pta =item[GBTT_PTA]
            lateObjectInstance.gbtt_ptd =item[GBTT_PTD]
            lateObjectInstance.late_canc_reason =item[LATE_CANC_REASON]
            lateObjectInstance.location=item[LOCATION]
            lateObjectInstance.date_of_service=date_of_service
            if item[ACTUAL_TA] != '' and item[GBTT_PTA] != '':
                lateObjectInstance.delay_time = LateObject.calculate_delay(int(item[ACTUAL_TA]),int(item[GBTT_PTA]))
            else: lateObjectInstance.delay_time = 0
            if lateObjectInstance.delay_time > 1:
                if date_of_service in lateDictionary:
                    list = lateDictionary[date_of_service]
                    list.append(lateObjectInstance)
                    lateDictionary[date_of_service] = list
                else:
                    lateDictionary[date_of_service] = [lateObjectInstance]

    #At this point we should have only one item in the dictionary
    if date_of_service in lateDictionary:
        if len(lateDictionary[date_of_service]) == 1:
            print('found for the date = ' + date_of_service)
            return lateDictionary[date_of_service][0]
        else: print ("Multiple events found")
    lateDictionary[date_of_service] = {}
    return lateDictionary'''

'''def matchingLateTrainObjects(departureLocation, arrivalLocation, serviceJson):
    arrivalLocationObject = [d for d in serviceJson[LOCATIONS] if d[LOCATION] == arrivalLocation][0]
    #arrivalLocationObject = arrivalLocationObjects[0] if arrivalLocationObjects else None
    if(arrivalLocationObject != None):
        arrivallateObjectInstance = createLateObject(arrivalLocationObject,serviceJson[DATE_OF_SERVICE],departureLocation)
        departurelateObjectInstance = createLateObject([d for d in serviceJson[LOCATIONS] if d[LOCATION] == departureLocation][0],serviceJson[DATE_OF_SERVICE],departureLocation)
        return arrivallateObjectInstance, departurelateObjectInstance'''

'''def createLateObject(item,date_of_service,departureLocation):
    lateObjectInstance = LateObject()
    lateObjectInstance.actual_ta = item[ACTUAL_TA]
    lateObjectInstance.actual_td = item[ACTUAL_TD]
    lateObjectInstance.gbtt_pta =item[GBTT_PTA]
    lateObjectInstance.gbtt_ptd =item[GBTT_PTD]
    lateObjectInstance.late_canc_reason =item[LATE_CANC_REASON]
    lateObjectInstance.location=item[LOCATION]
    lateObjectInstance.date_of_service=date_of_service
    lateObjectInstance.departureStation= (departureLocation == item[LOCATION])
    if item[ACTUAL_TA] != '' and item[GBTT_PTA] != '':
        lateObjectInstance.delay_time = LateObject.calculate_delay(item[ACTUAL_TA],item[GBTT_PTA])
    else: lateObjectInstance.delay_time = 0
    return lateObjectInstance'''