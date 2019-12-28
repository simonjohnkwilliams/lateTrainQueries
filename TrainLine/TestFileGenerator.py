import configparser
import requests
from datetime import date,datetime,timedelta
import json
import os
import fnmatch
from requests.exceptions import HTTPError
#from TrainLine import LateObject
from LateObject import LateObject

DATE_FORMAT = "%Y-%m-%d"
DAYS_BACK = 31
OUTBOUND_ATTRIBUTE_MESSAGE_DIR = os.getcwd() + '/../test/files'
INBOUND_ATTRIBUTE_MESSAGE_DIR = os.getcwd() + '/../test/files'
OUTBOUND_SERVICE_MESSAGE_DIR = os.getcwd() + '/../test/files'
INBOUND_SERVICE_MESSAGE_DIR = os.getcwd() + '/../test/files'
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


def writeServiceMetricsTestData(from_station, to_station,from_time, to_time, to_date,days_difference, fileName):
    #seems like there might be a limit to the amount of daa being returned.
    #need to pull in a loop.....
    for counter in range(0, days_difference):
        d = (to_date - timedelta(days=counter)).strftime(DATE_FORMAT)
        print ("getting all data for date - " + str(d))
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
        except Exception as err:
            print(f'Other error occurred: {err}')
        #now we write out the file to the test dir.
        fname = fileName + str(counter) + ".txt"
        writeFile(fname,json.dumps(response.json()))

def writeFile(fileName,data):

    f = open(fileName, "w+")
    f.write(data)
    f.close()

def writeAttributeMessageTestData(pidList,fileName):
    jsonList = []
    counter =1
    for pid in pidList:
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
        writeFile(fileName + str(counter) + ".txt", json.dumps(response.json()))
        counter += 1
    return

def generatePidList(serviceMetricJson):
    ridList = []
    for key in serviceMetricJson["Services"]:
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

def generateAttrbuteDictionary(days_back,filename):
        jsonlist = []
        for counter in range(1, days_back):
            #print('Reading file = ' + filename +str(counter)+'.txt')
            jsonlist.append(readjson(filename+str(counter)+'.txt'))
        return jsonlist

def generateLateTrainObject(departureLocation, arrivalLocation, date_of_service):
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
            lateObjectInstance.date_of_service=date_of_service
            lateObjectInstance.departureStation= (departureLocation == item[LOCATION])
            if item[ACTUAL_TA] != '' and item[GBTT_PTA] != '':
                lateObjectInstance.delay_time = LateObject.calculate_delay(item[ACTUAL_TA],item[GBTT_PTA])
            else: lateObjectInstance.delay_time = 0
            if lateObjectInstance.delay_time > 1:
                lateObjectArray.append(lateObjectInstance)
    return lateObjectArray

def generateLateTrainDictionary(location, date_of_service):
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
    return lateDictionary

def filesInDir(dir,filename):
    counter = 0
    for file in os.listdir(dir):
        if fnmatch.fnmatch(file, filename +'*'):
            counter +=1
    return counter

def getLatestTrainObject(listOfTrainObjects):
    if len(listOfTrainObjects) !=0:
        latestDeparture = listOfTrainObjects[0][0]
        latestArrival = listOfTrainObjects[0][1]
    else: return [LateObject,LateObject]
    latestTrainObjects = [latestDeparture,latestArrival]
    for trainObjectArray in listOfTrainObjects:
        trainObjectDepart = trainObjectArray[0]
        trainObjectArrival = trainObjectArray[1]
        if int(trainObjectArrival.delay_time) > latestTrainObjects[1].delay_time:
            latestTrainObjects = [trainObjectDepart,trainObjectArrival]
    return latestTrainObjects

def writeLateTrainsToFile(fileName,trainObjectList, arrival):

    output = 'Outbound Train To ' + arrival + '\n'
    output = output + 'Date, Departure Time, Delay Time' + '\n'
    for trainObjectArray in trainObjectList:
        departTrain = trainObjectArray[0]
        arrivalTrain = trainObjectArray[1]
        if departTrain.date_of_service != None:
            output =  output + str(departTrain.date_of_service) + ','+ str(departTrain.gbtt_pta) +',' + str(arrivalTrain.delay_time) + '\n'

    writeFile(os.getcwd() +'/Results/'+ fileName+'.csv',output)

if __name__== "__main__":
    #generate to journey
    generateOutbound = True
    generateInbound = True

    if(generateOutbound):
        if(False):
            writeServiceMetricsTestData('GOD','WAT','0400','1300',date.today(), DAYS_BACK, OUTBOUND_ATTRIBUTE_MESSAGE)
            #all serviceMessages created
            outboundPidList = []
            for outboundCounter in range (0,DAYS_BACK):
                outboundPidList.append(generatePidList(readjson(OUTBOUND_ATTRIBUTE_MESSAGE + str(outboundCounter)+ '.txt')))
            for outboundPidCounter, outboundPids in enumerate(outboundPidList):
                writeAttributeMessageTestData(outboundPids,OUTBOUND_SERVICE_MESSAGE + str(outboundPidCounter))
        listOfJsonLists = []
        for outboundFileCounter in range (0,30):
            string = OUTBOUND_SERVICE_MESSAGE.replace(OUTBOUND_ATTRIBUTE_MESSAGE_DIR + '/', '') + str(outboundFileCounter)
            listOfJsonLists.append(generateAttrbuteDictionary(filesInDir(OUTBOUND_ATTRIBUTE_MESSAGE_DIR, string),OUTBOUND_SERVICE_MESSAGE + str(outboundFileCounter)))
        #we now have a list of all the json objects for each train journey. each of the list elements should correspond to a date.
        #filter out all of the list items to the latest train on each day.
        lateTrainDictionary = {}
        for jsonLists in listOfJsonLists:
            #this is now the list for the date
            for serviceAttribute in jsonLists:
                if serviceAttribute != None and SERVICE_ATTRIBUTES_DETAILS in serviceAttribute and DATE_OF_SERVICE in serviceAttribute[SERVICE_ATTRIBUTES_DETAILS] and LOCATIONS in serviceAttribute[SERVICE_ATTRIBUTES_DETAILS]:
                    lateTrainArray = generateLateTrainObject('GOD','WAT',serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE])
                    if len(lateTrainArray) == 2 and lateTrainArray[0] != None and lateTrainArray[1] != None:
                        dateOfService = lateTrainArray[0].date_of_service
                        if dateOfService in lateTrainDictionary:
                            ltl = lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]]
                            ltl.append(lateTrainArray)
                            lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]] = ltl
                        else:
                             lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]] = [lateTrainArray]
        #we now have the dictionary of all the items according to date
        latestTrainList = []
        for dateList in lateTrainDictionary.values():
            #we now have a date for trains - sort through this and pullout the one with the latest time.
            #need to sort this list by date.
            latestTrainList.append(getLatestTrainObject(dateList))

        #we now have a list of the lastest train objects they now need to be formatted correctly and send out
        latestTrainList.sort(key=lambda x: x[0].date_of_service, reverse=True)
        writeLateTrainsToFile('outboundLateTrains',latestTrainList,'WAT')

    #generate from journey
    if(generateInbound):
        if(True):
            writeServiceMetricsTestData('WAT','GOD','1200','2200',date.today(), DAYS_BACK, INBOUND_ATTRIBUTE_MESSAGE)
            #all serviceMessages created
            outboundPidList = []
            for outboundCounter in range (0,DAYS_BACK):
                outboundPidList.append(generatePidList(readjson(INBOUND_ATTRIBUTE_MESSAGE + str(outboundCounter)+ '.txt')))
            for outboundPidCounter, outboundPids in enumerate(outboundPidList):
                writeAttributeMessageTestData(outboundPids,OUTBOUND_SERVICE_MESSAGE + str(outboundPidCounter))
        listOfJsonLists = []
        for outboundFileCounter in range (0,30):
            string = INBOUND_SERVICE_MESSAGE.replace(INBOUND_ATTRIBUTE_MESSAGE_DIR + '/', '') + str(outboundFileCounter)
            listOfJsonLists.append(generateAttrbuteDictionary(filesInDir(INBOUND_ATTRIBUTE_MESSAGE_DIR, string),INBOUND_SERVICE_MESSAGE + str(outboundFileCounter)))
        #we now have a list of all the json objects for each train journey. each of the list elements should correspond to a date.
        #filter out all of the list items to the latest train on each day.
        lateTrainDictionary = {}
        for jsonLists in listOfJsonLists:
            for serviceAttribute in jsonLists:
                if serviceAttribute != None and SERVICE_ATTRIBUTES_DETAILS in serviceAttribute and DATE_OF_SERVICE in serviceAttribute[SERVICE_ATTRIBUTES_DETAILS] and LOCATIONS in serviceAttribute[SERVICE_ATTRIBUTES_DETAILS]:
                    lateTrainArray = generateLateTrainObject('GOD','WAT',serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE])
                    if len(lateTrainArray) == 2 and lateTrainArray[0] != None and lateTrainArray[1] != None:
                        dateOfService = lateTrainArray[0].date_of_service
                        if dateOfService in lateTrainDictionary:
                            ltl = lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]]
                            ltl.append(lateTrainArray)
                            lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]] = ltl
                        else:
                            lateTrainDictionary[serviceAttribute[SERVICE_ATTRIBUTES_DETAILS][DATE_OF_SERVICE]] = [lateTrainArray]
        #we now have the dictionary of all the items according to date
        latestTrainList = []
        for dateList in lateTrainDictionary.values():
            #we now have a date for trains - sort through this and pullout the one with the latest time.
            latestTrainList.append(getLatestTrainObject(dateList))

        #we now have a list of the lastest train objects they now need to be formatted correctly and send out
        writeLateTrainsToFile('inboundLateTrains',latestTrainList,'GOD')

    print("congratulations all test data has been downloaded.")
