import json
import os

class messageCreator:

    def getServiceMessgae(self):
        return messageCreator.readjson('../test/files/serviceAttributesOutbound.txt')

    def getServiceAttributes(self):
        jsonlist = []
        for counter in range(1, 40):
            print('Reading file = ' + '../test/files/serviceAttributesInbound'+str(counter)+'.json')
            jsonlist.append(messageCreator.readjson(os.getcwd() + '/../test/files/serviceAttributesOutboundTestdata'+str(counter)+'.txt'))
        return jsonlist

    def readjson(fileName):
        with open(fileName) as json_file:
            data = json.load(json_file)
        return data
