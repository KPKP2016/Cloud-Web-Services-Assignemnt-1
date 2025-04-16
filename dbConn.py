import MySQLdb

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'passwd': '12bms34bsm56nk',
    'db': 'AdventureWorks2019',
}
  

try:
    conn = MySQLdb.connect(**db_config)
    print("Database connection successful")
except MySQLdb.Error as e:
    print(f"Error connecting to database: {e}")