import datetime

class LateObject:

    location = ''
    gbtt_ptd = ''
    gbtt_pta= ''
    actual_td= ''
    actual_ta= ''
    late_canc_reason= ''
    date_of_service= ''
    delay_time= ''
    departureStation= ''

    def __init_(self,location, gbtt_ptd="",gbtt_pta="",actual_td="",actual_ta="",late_canc_reason="",date_of_service="",delay_time=0,departureStation=False):
        self.location = location
        self.gbtt_ptd = gbtt_ptd
        self.gbtt_pta = gbtt_pta
        self.actual_td = actual_td
        self.actual_ta = actual_ta
        self.late_canc_reason = late_canc_reason
        self.date_of_service = date_of_service
        self.delay_time = delay_time
        self.departureStation = departureStation

    def __str__(self):
        return "The train on - " + self.date_of_service + " has the following attributes /n late reason - " + self.late_canc_reason + " scheduled " \
        "arrival " + self.gbtt_pta + " and the actual arrival = " + self.actual_ta

    def calculate_delay(actual_time_arrival, scheduled_time_arrival):
        #need to convert these to times and find out the differnece.
        actualIsoTime = datetime.timedelta(hours=int(actual_time_arrival[:2]),minutes=int(actual_time_arrival[2:4]))
        scheduledIsoTime = datetime.timedelta(hours=int(scheduled_time_arrival[:2]),minutes=int(scheduled_time_arrival[2:4]))
        delay = ((actualIsoTime - scheduledIsoTime).total_seconds())/60
        if (delay) < 0:
            return 0
        else:
            return int(delay)
