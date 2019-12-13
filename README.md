# Late Train Query Engine

This program queires the Darwin API for train times from SWR and returns the data from this. 

By default you pass in a set of arguments which include the 

Departure station
Arrival Station
Start search time
End Search time
Start search data
End Search date. 

In the format - GOD WAT 0600 1200 2019-11-01 2019-11-30

As the API for Darwin is asynchronous there are two seperate calls one to the serviceMetrics endpoint to get all of the id's of the trains running at that time, then secondly to the serviceDetails endpoint to get the specific train times. 

At the moment it's pretty specific and only gives you back the latest trains in a range and outputs them to a local file.

# Road map

1.) Clean up the code 
2.) Break down the classes
3.) Split the write of to files for data to be parallell. 
4.) Add an option to run it directly from the messgaes without writing to disk. 
5.) Split it out into Lambda functions
6.) Build the terraform for the above. 
