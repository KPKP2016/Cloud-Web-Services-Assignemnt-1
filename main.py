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

class TokenResponse(BaseModel):
    token: str
    message: str

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
def register(auth_details: AuthDetails):
    if any(x['username'] == auth_details.Username for x in users):
        raise HTTPException(status_code=400, detail='Username is taken')
    hashed_password = auth_handler.get_password_hash(auth_details.Password)
    users.append({
        'username': auth_details.Username,
        'password': hashed_password    
    })
    return {"message": "User registered successfully"}


@app.post('/token', response_model=TokenResponse)
def get_token(auth_details: AuthDetails):
    user = None
    for x in users:
        if x['username'] == auth_details.Username:
            user = x
            break
    
    if (user is None) or (not auth_handler.verify_password(auth_details.Password, user['password'])):
        raise HTTPException(status_code=401, detail='Invalid username and/or password')
    token = auth_handler.encode_token(user['username'])
    return TokenResponse(token=token, message="Token generated successfully")


@app.put('/token', response_model=TokenResponse)
def refresh_token(auth_details: AuthDetails):
    user = None
    for x in users:
        if x['username'] == auth_details.Username:
            user = x
            break
    
    if (user is None) or (not auth_handler.verify_password(auth_details.Password, user['password'])):
        raise HTTPException(status_code=401, detail='Invalid username and/or password')
    token = auth_handler.encode_token(user['username'])
    return TokenResponse(token=token, message="Token refreshed successfully")


@app.delete('/token')
def revoke_token(username: str = Depends(auth_handler.auth_wrapper)):
    # In a real application, you would invalidate the token
    # Since we're using JWT without a database for tokens, we'll simulate token revocation
    return {"message": f"Token for user {username} has been revoked successfully"}


@app.get("/products/all", response_model=List[Products], tags=["Products"])
def get_all_products():
    """
    Get a list of all products (limited to 50)
    """
    cursor = conn.cursor()
    query = "SELECT ProductID, Name FROM Production_Product LIMIT 50"
    cursor.execute(query)
        
    item = cursor.fetchall()
    cursor.close()
    if item is None:
        raise HTTPException(status_code=404, detail="Items not found")
    item = [Products(ProductID=productitem[0], Name=productitem[1]) for productitem in item]
    return item


@app.get("/products/reorder", response_model=List[ProductQuantities], tags=["Products"])
def get_all_reorder_products():
    """
    Get all products that need to be reordered (inventory quantity lower than reorder point)
    """
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


@app.put("/products/change/listprice/{product_id}/{list_price}", tags=["Products"])
def update_list_price(product_id: int, list_price: float, username: str = Depends(auth_handler.auth_wrapper)):
    """
    Update the list price of a product (Protected endpoint)
    """
    cursor = conn.cursor()
    # Error handling ensures that the ProductID/product exists before changes are made.
    query = ("SELECT ProductID FROM AdventureWorks2019.Production_Product WHERE ProductID=%s;")
    cursor.execute(query, (product_id,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    # Query, execute and commit will PUT the new data to the database.
    query = ("UPDATE AdventureWorks2019.Production_Product SET ListPrice=%s, ModifiedDate=Now() WHERE ProductID=%s;")
    cursor.execute(query, (list_price, product_id))
    conn.commit()
    cursor.close()
    # Return successful response
    return {"message": f"Price for product {product_id} has been updated to {list_price}", "updated_by": username}


@app.delete("/products/delete/review/{product_review_id}", tags=["Products"])
def delete_product_review(product_review_id: int, username: str = Depends(auth_handler.auth_wrapper)):
    """
    Delete a product review by ID (Protected endpoint)
    """
    cursor = conn.cursor()
    # Error handling ensures that ProductReviewID/product review exists before it is deleted.
    query = ("SELECT ProductReviewID FROM AdventureWorks2019.Production_ProductReview WHERE ProductReviewID=%s;")
    cursor.execute(query, (product_review_id,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=404, detail="Review not found")
    # Query, execute and commit below will DELETE the specified data from the database.
    query = ("DELETE FROM AdventureWorks2019.Production_ProductReview WHERE ProductReviewID=%s;")
    cursor.execute(query, (product_review_id,))
    conn.commit()
    cursor.close()
    # Return successful response
    return {"message": f"Review {product_review_id} has been deleted successfully", "deleted_by": username}


@app.post("/products/new/review/{product_id}/{reviewer_name}/{email_address}/{rating}", tags=["Products"])
def add_new_product_review(product_id: int, reviewer_name: str, email_address: str, rating: int, comment: str, username: str = Depends(auth_handler.auth_wrapper)):
    """
    Add a new product review (Protected endpoint)
    """
    cursor = conn.cursor()
    # Error handling and data consistency, ensures that the ProductID/product to be reviewed already exist in the database.
    query = ("SELECT ProductID FROM AdventureWorks2019.Production_Product WHERE ProductID=%s;")
    cursor.execute(query, (product_id,))
    item = cursor.fetchone()
    if item is None:
        raise HTTPException(status_code=404, detail="Product does not exist")
    # Data consistency ensures that the rating can only be between 1 and 5.
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Product is only rated between 1 and 5")
    # Retrieves the new unique primary key identifier for the INSERT INTO query.
    query = ("SELECT IFNULL((SELECT (MAX(ProductReviewID) +1) FROM AdventureWorks2019.Production_ProductReview), '1');")
    cursor.execute(query)
    product_review_id = cursor.fetchone()
    # Query, execute and commit below will POST the data to the database.
    query = ("INSERT INTO AdventureWorks2019.Production_ProductReview VALUES (%s, %s, %s, (NOW()), %s, %s, %s, (NOW())); ")
    cursor.execute(query, (product_review_id, product_id, reviewer_name, email_address, rating, comment))
    conn.commit()
    cursor.close()
    # Return successful response
    return {
        "message": "New product review has been added successfully",
        "reviewed_by": username,
        "product_id": product_id
    }


@app.get("/employees/payrates", response_model=List[EmployeePay], tags=["Employees"])
def get_employee_pay_rates(username: str = Depends(auth_handler.auth_wrapper)):
    """
    Get all employee pay rates (Protected endpoint)
    """
    cursor = conn.cursor()
    query = """
    SELECT e.BusinessEntityID, e.NationalIDNumber, 
           CONCAT(p.FirstName, ' ', p.LastName) AS Name, 
           e.OrganizationLevel, e.JobTitle, r.Rate, r.PayFrequency
    FROM HumanResources_Employee e
    JOIN Person_Person p ON e.BusinessEntityID = p.BusinessEntityID
    JOIN HumanResources_EmployeePayHistory r ON e.BusinessEntityID = r.BusinessEntityID
    ORDER BY e.BusinessEntityID
    LIMIT 50
    """
    cursor.execute(query)
    employees = cursor.fetchall()
    cursor.close()
    
    if not employees:
        raise HTTPException(status_code=404, detail="No employee pay data found")
    
    result = [
        EmployeePay(
            BusinessEntityID=emp[0],
            NationalIDNumber=emp[1],
            Name=emp[2],
            OrganizationLevel=emp[3],
            JobTitle=emp[4],
            Rate=float(emp[5]),
            PayFrequency=emp[6]
        ) for emp in employees
    ]
    
    return result