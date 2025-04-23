from itertools import product
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional
from dbConn import conn
from auth import AuthHandler
from schemas import AuthDetails
    
app = FastAPI()
# Pydantic model to define the schema of the data for GET PUT POST DELETE
class Products(BaseModel):
    ProductID: int 
    Name: str 
class ProductQuantities(BaseModel):
    ProductID: int
    Name: str
    ProductNumber: str
    TotalQuantity: int
    SafetyStockLevel: int
    ReorderPoint: int
    StandardCost: float
    ListPrice: float

class EmployeePay(BaseModel):
    BusinessEntityID: int
    NationalIDNumber: int
    Name: Optional[str] = None
    OrganizationLevel: Optional[int] = None
    JobTitle: Optional[str] = None
    Rate: float
    PayFrequency:int

# Initialize authentication handler
auth_handler = AuthHandler()
users = []


# POST endpoint to register a new user
@app.post('/register', status_code=201)
def register(auth_details: AuthDetails):
    # Check if the username already exists
    if any(x['username'] == auth_details.username for x in users):
        raise HTTPException(status_code=400, detail='Username is taken')
    # Hash the password and store the user details
    hashed_password = auth_handler.get_password_hash(auth_details.password)
    users.append({
        'username': auth_details.username,
        'password': hashed_password    
    })
    return

# POST endpoint to login a user and return a JWT token
@app.post('/login')
def login(auth_details: AuthDetails):
    user = None
    # Find the user by username
    for x in users:
        if x['username'] == auth_details.username:
            user = x
            break

    # Verify the password and check if the user exists
    if (user is None) or (not auth_handler.verify_password(auth_details.password, user['password'])):
        raise HTTPException(status_code=401, detail='Invalid username and/or password')
    # Generate a JWT token for the user
    token = auth_handler.encode_token(user['username'])
    return { 'token': token }

# GET endpoint that retrieves all employee details from the database.
@app.get("/employees/{employeeId}")
def get_employee_details(employeeId: int):
    cursor = conn.cursor()
    # SQL query to fetch employee details
    query = """
    SELECT e.BusinessEntityID, e.NationalIDNumber, p.FirstName, p.LastName, e.JobTitle, eph.Rate, eph.PayFrequency
    FROM AdventureWorks2019.HumanResources_Employee e
    JOIN AdventureWorks2019.Person_Person p ON e.BusinessEntityID = p.BusinessEntityID
    JOIN AdventureWorks2019.HumanResources_EmployeePayHistory eph ON e.BusinessEntityID = eph.BusinessEntityID
    WHERE e.BusinessEntityID = %s
    """
    cursor.execute(query, (employeeId,))
    
    item = cursor.fetchone()
    cursor.close()
    # Raise an exception if the employee is not found
    if item is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Return the employee details
    return {
        "BusinessEntityID": item[0],
        "NationalIDNumber": item[1],
        "Name": f"{item[2]} {item[3]}",
        "JobTitle": item[4],
        "Rate": item[5],
        "PayFrequency": item[6]
    }

# The GET endpoint will retrieve all products that have the SUM of inventory quantity lower than the stated reorder point.
@app.get("/products/reorder", response_model=List[ProductQuantities],)
def get_all_reorder_products():
    cursor = conn.cursor()
    # Query, execute and fetchall below are used to retrieve
    cursor.execute("SELECT Production_Product.ProductID, Production_Product.Name, Production_Product.ProductNumber, SUM(Production_ProductInventory.Quantity), Production_Product.SafetyStockLevel, Production_Product.ReorderPoint, StandardCost, ListPrice FROM AdventureWorks2019.Production_Product LEFT JOIN Production_ProductInventory ON Production_Product.ProductID = Production_ProductInventory.ProductID GROUP BY ProductID HAVING SUM(Production_ProductInventory.Quantity) <= Production_Product.ReorderPoint;") #SQL query executed
    item = cursor.fetchall()
    # Error handling in case there are no products matching this query.
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="No product found to reorder")
    cursor.close()
    item = [ProductQuantities(ProductID=productitem[0], Name=productitem[1], ProductNumber=productitem[2], TotalQuantity=productitem[3], SafetyStockLevel=productitem[4], ReorderPoint=productitem[5], StandardCost=productitem[6], ListPrice=productitem[7]) for productitem in item]
    return item

# PUT endpoint to update product list price
@app.put("/products/change/listprice/{productId}/{listPrice}")
def update_list_price(productId: int, listPrice: float):
    cursor = conn.cursor()
    # Error handling ensures that the ProductID/product exists before changes are made.
    query = ("SELECT ProductID FROM AdventureWorks2019.Production_Product WHERE ProductID=%s;")
    cursor.execute (query, (productId,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=400, detail="Product not found")
    # Query, execute and commit will PUT the new data to the database.
    query = ("UPDATE AdventureWorks2019.Production_Product SET ListPrice=%s, ModifiedDate=Now() WHERE ProductID=%s;")
    cursor.execute (query, (listPrice, productId))
    conn.commit()
    cursor.close()
    # HTTPException is used to confirm that the PUT has completed.
    raise HTTPException(status_code=200, detail="Price has been updated")

# POST endpoint to add product inventory
@app.post("/inventory/add/{productId}/{locationId}/{quantity}")
def add_product_inventory(productId: int, locationId: int, quantity: int):
    cursor = conn.cursor()
    
    # Check if product exists
    query = ("SELECT ProductID FROM AdventureWorks2019.Production_Product WHERE ProductID=%s;")
    cursor.execute(query, (productId,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=400, detail="Product does not exist")
    
    # Check if location exists
    query = ("SELECT LocationID FROM AdventureWorks2019.Production_Location WHERE LocationID=%s;")
    cursor.execute(query, (locationId,))
    location = cursor.fetchone()
    if location is None:
        raise HTTPException(status_code=400, detail="Location does not exist")
    
    # Check if inventory already exists at this location
    query = ("SELECT * FROM AdventureWorks2019.Production_ProductInventory WHERE ProductID=%s AND LocationID=%s;")
    cursor.execute(query, (productId, locationId))
    existing_inventory = cursor.fetchone()
    
    if existing_inventory is not None:
        # Update existing inventory
        query = ("UPDATE AdventureWorks2019.Production_ProductInventory SET Quantity=Quantity+%s, ModifiedDate=NOW() "
                "WHERE ProductID=%s AND LocationID=%s;")
        cursor.execute(query, (quantity, productId, locationId))
    else:
        # Add new inventory entry
        query = ("INSERT INTO AdventureWorks2019.Production_ProductInventory (ProductID, LocationID, Quantity, ModifiedDate) "
                "VALUES (%s, %s, %s, NOW());")
        cursor.execute(query, (productId, locationId, quantity))
    
    conn.commit()
    cursor.close()
    
    return {
        "message": "Inventory has been updated successfully",
        "product_id": productId,
        "location_id": locationId,
        "quantity_added": quantity
    }

# DELETE endpoint that allows review to be deleted from the Production_ProductReview table.
@app.delete("/products/delete/review/{productReviewId}",tags=["Protected"])
def delete_product_review(productReviewId: int, username: str = Depends(auth_handler.auth_wrapper)):
    cursor = conn.cursor()
    # Error handling ensures that ProductReviewID/product review exists before it is deleted.
    query = ("SELECT ProductReviewID FROM AdventureWorks2019.Production_ProductReview WHERE ProductReviewID=%s;")
    cursor.execute (query, (productReviewId,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=400, detail="Review not found")
    # Query, execute and commit below will DELETE the specified data from the database.
    query = ("DELETE FROM AdventureWorks2019.Production_ProductReview WHERE ProductReviewID=%s;")
    cursor.execute (query, (productReviewId,))
    conn.commit()
    cursor.close()
    # HTTPException is used to confirm that the DELETE has completed successfully.
    raise HTTPException(status_code=200, detail="Review has been deleted")



### Protected Endpoints ###

# Protected PUT endpoint to update employee pay rate
@app.put("/employees/update/rate/{employeeId}/{rate}", tags=["Protected"])
def update_employee_rate(employeeId: int, rate: float, username: str = Depends(auth_handler.auth_wrapper)):
    cursor = conn.cursor()
    # Error handling ensures that the employee exists before changes are made
    query = ("SELECT BusinessEntityID FROM AdventureWorks2019.HumanResources_EmployeePayHistory WHERE BusinessEntityID=%s;")
    cursor.execute(query, (employeeId,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=400, detail="Employee not found")
    
    # Validate pay rate is reasonable
    if rate <= 0:
        raise HTTPException(status_code=400, detail="Pay rate must be greater than zero")
    
    # Update employee pay rate
    query = ("UPDATE AdventureWorks2019.HumanResources_EmployeePayHistory SET Rate=%s, ModifiedDate=Now() WHERE BusinessEntityID=%s;")
    cursor.execute(query, (rate, employeeId))
    conn.commit()
    cursor.close()
    
    return {
        "message": "Employee pay rate has been updated successfully",
        "updated_by": username,
        "employee_id": employeeId,
        "new_rate": rate
    }


# Protected POST endpoint to add a new product review
@app.post("/products/new/review/{productId}/{reviewerName}/{emailAddress}/{rating}", tags=["Protected"])
def add_new_product_review(productId: int, reviewerName: str, emailAddress: str, rating: int, comment: str, username: str = Depends(auth_handler.auth_wrapper)):
    cursor = conn.cursor()
    # Error handling and data consistency, ensures that the ProductID/product to be reviewed already exist in the database.
    query = ("SELECT ProductID FROM AdventureWorks2019.Production_Product WHERE ProductID=%s;")
    cursor.execute (query, (productId,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=400, detail="Product does not exist")
    # Data consistency ensures that the rating can only be between 1 and 5.
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Product is only rated between 1 and 5")
    # Retrieves the new unique primary key identifier for the INSERT INTO query.
    query = ("SELECT IFNULL((SELECT (MAX(ProductReviewID) +1) FROM AdventureWorks2019.Production_ProductReview), '1');")
    cursor.execute (query)
    productReviewId = cursor.fetchone()
    # Query, execute and commit below will POST the data to the database.
    query = ("INSERT INTO AdventureWorks2019.Production_ProductReview VALUES (%s , %s, %s, (NOW()), %s, %s, %s, (NOW())); ")
    cursor.execute (query, (productReviewId, productId, reviewerName, emailAddress, rating, comment))
    conn.commit()
    cursor.close()
    # HTTPException is used to confirm that the POST has succeeded.
    #raise HTTPException(status_code=200, detail="New product review has been added")
    return {
        "message": "New product review has been added successfully",
        "reviewed_by": username,
        "product_id": productId
    }


# Protected DELETE endpoint to remove product from inventory
@app.delete("/inventory/remove/{productId}/{locationId}")
def remove_product_inventory(productId: int, locationId: int):
    cursor = conn.cursor()
    
    # Check if inventory exists at this location
    query = ("SELECT * FROM AdventureWorks2019.Production_ProductInventory WHERE ProductID=%s AND LocationID=%s;")
    cursor.execute(query, (productId, locationId))
    existing_inventory = cursor.fetchone()
    
    if existing_inventory is None:
        raise HTTPException(status_code=404, detail="No inventory found for this product at this location")
    
    # Delete inventory entry
    query = ("DELETE FROM AdventureWorks2019.Production_ProductInventory WHERE ProductID=%s AND LocationID=%s;")
    cursor.execute(query, (productId, locationId))
    conn.commit()
    cursor.close()
    
    return {
        "message": "Inventory has been removed successfully",
        "product_id": productId,
        "location_id": locationId
    }
