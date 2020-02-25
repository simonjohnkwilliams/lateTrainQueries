import os
from datetime import date,datetime,timedelta

DATE_FORMAT = "%Y-%m-%d"
DAYS_BACK = 9
MESSAGE_DIR = os.getcwd() + '/../test/files'
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
SERVICE_FILE_LOCATION_STRING = 'SERVICE_FILE_LOCATION_STRING'
SERVICE_DIR_LOCATION_STRING = 'SERVICE_DIR_LOCATION_STRING'
START_LOCATION_STRING = 'START_LOCATION'
TO_LOCATION_STRING = 'TO_LOCATION'
START_TIME = 'START_TIME'
END_TIME = 'END_TIME'
RESULT_FILE_STRING = 'LATE_TRAIN_STRING'
RESULT_FILE_OUTBOUND = 'outboundLateTrains'
RESULT_FILE_INBOUND = 'inboundLateTrains'

def getJson(argsJson):
    if (len(argsJson)==1):
        return {
            OUTBOUND_JOURNEY:{
                DEPARTURE_STATION:"GOD",
                TO_LOCATION_STRING:"WAT",
                START_TIME:"0400",
                END_TIME:"1300",
                START_DATE_STRING:(date.today() - timedelta(days=2)),
                DAYS_BACK_STRING:DAYS_BACK,
                FILE_LOCATION_STRING:OUTBOUND_ATTRIBUTE_MESSAGE,
                DIR_LOCATION_STRING:OUTBOUND_ATTRIBUTE_MESSAGE_DIR,
                SERVICE_FILE_LOCATION_STRING:OUTBOUND_SERVICE_MESSAGE,
                RESULT_FILE_STRING:RESULT_FILE_OUTBOUND,

            },
            INBOUND_JOURNEY:{
                DEPARTURE_STATION:"WAT",
                TO_LOCATION_STRING:"GOD",
                START_TIME:"1200",
                END_TIME:"2359",
                START_DATE_STRING:(date.today() - timedelta(days=2)),
                DAYS_BACK_STRING:DAYS_BACK,
                FILE_LOCATION_STRING:INBOUND_ATTRIBUTE_MESSAGE,
                DIR_LOCATION_STRING:INBOUND_ATTRIBUTE_MESSAGE_DIR,
                SERVICE_FILE_LOCATION_STRING:INBOUND_SERVICE_MESSAGE,
                RESULT_FILE_STRING:RESULT_FILE_INBOUND
            }
        }
    serviceMapJourneylocal = argsJson
    if argsJson[START_DATE_STRING]==None:
        serviceMapJourneylocal[START_DATE_STRING] = date.today()
    if argsJson[DAYS_BACK_STRING]==None:
        serviceMapJourneylocal[DAYS_BACK_STRING] = DAYS_BACK
    return serviceMapJourneylocal