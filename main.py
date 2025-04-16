from itertools import product
from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List, Optional
from dbConn import conn
from auth import AuthHandler
    
app = FastAPI()
# Pydantic model to define the schema of the data for GET PUT POST DELETE

class Products(BaseModel):
    ProductID: int 
    Name: str 

class AuthDetails(BaseModel):
    Username: str 
    Password: str 

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

auth_handler = AuthHandler()
users = []

@app.post('/register', status_code=201)
def register(auth_details: AuthDetails, ):
    if any(x['username'] == auth_details.username for x in users):
        raise HTTPException(status_code=400, detail='Username is taken')
    hashed_password = auth_handler.get_password_hash(auth_details.password)
    users.append({
        'username': auth_details.username,
        'password': hashed_password    
    })
    return


@app.post('/login')
def login(auth_details: AuthDetails):
    user = None
    for x in users:
        if x['username'] == auth_details.username:
            user = x
            break
    
    if (user is None) or (not auth_handler.verify_password(auth_details.password, user['password'])):
        raise HTTPException(status_code=401, detail='Invalid username and/or password')
    token = auth_handler.encode_token(user['username'])
    return { 'token': token }

    


@app.get("/products/all", response_model=List[Products])
def unprotected():
    cursor = conn.cursor()
    query = "SELECT ProductID, Name FROM Production_Product LIMIT 50"
    cursor.execute(query)
        
    item = cursor.fetchall()
    cursor.close()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item = [Products(ProductID=productitem[0], Name=productitem[1]) for productitem in item]
    return item

#@app.get('/protected')
#def protected(username=Depends(auth_handler.auth_wrapper)):
    #return { 'name': username }

###
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

    


# PUT endpoint that allows list price information stored in the Production_Product table to be changed/updated.
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