import MySQLdb

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'passwd': '12bms34bsm56nk',
    'db': 'AdventureWorks2019',
}
  
# Create a connection to the database
conn = MySQLdb.connect(**db_config)              
 