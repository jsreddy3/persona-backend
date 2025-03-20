import logging
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.admin import router as admin_router
from dependencies.auth import get_admin_access

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Override admin access for testing
async def mock_admin_access():
    return True

# Create a test app
app = FastAPI()
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.dependency_overrides[get_admin_access] = mock_admin_access

# Create test client
client = TestClient(app)

def test_health_endpoint():
    """Test the health endpoint"""
    start_time = time.time()
    response = client.get("/api/admin/health")
    duration = time.time() - start_time
    
    logger.info(f"Health endpoint response time: {duration:.4f}s")
    logger.info(f"Response: {response.json()}")
    
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_dashboard_stats():
    """Test the dashboard stats endpoint"""
    start_time = time.time()
    response = client.get("/api/admin/analytics/dashboard")
    duration = time.time() - start_time
    
    logger.info(f"Dashboard stats response time: {duration:.4f}s")
    logger.info(f"Response status: {response.status_code}")
    
    # Check response status
    assert response.status_code == 200
    
    # Second call should be faster (cached)
    start_time = time.time()
    response = client.get("/api/admin/analytics/dashboard")
    cached_duration = time.time() - start_time
    
    logger.info(f"Dashboard stats cached response time: {cached_duration:.4f}s")
    logger.info(f"Cache speedup: {duration / cached_duration:.2f}x")

def test_activity_feed():
    """Test the activity feed endpoint"""
    start_time = time.time()
    response = client.get("/api/admin/analytics/activity?limit=5")
    duration = time.time() - start_time
    
    logger.info(f"Activity feed response time: {duration:.4f}s")
    logger.info(f"Response status: {response.status_code}")
    
    # Check response status
    assert response.status_code == 200
    
    # Second call should be faster (cached)
    start_time = time.time()
    response = client.get("/api/admin/analytics/activity?limit=5")
    cached_duration = time.time() - start_time
    
    logger.info(f"Activity feed cached response time: {cached_duration:.4f}s")
    logger.info(f"Cache speedup: {duration / cached_duration:.2f}x")

def test_users_endpoint():
    """Test the users endpoint"""
    start_time = time.time()
    response = client.get("/api/admin/users?page=1&limit=5")
    duration = time.time() - start_time
    
    logger.info(f"Users endpoint response time: {duration:.4f}s")
    logger.info(f"Response status: {response.status_code}")
    
    # Check response status
    assert response.status_code == 200
    
    # Second call should be faster (cached)
    start_time = time.time()
    response = client.get("/api/admin/users?page=1&limit=5")
    cached_duration = time.time() - start_time
    
    logger.info(f"Users endpoint cached response time: {cached_duration:.4f}s")
    logger.info(f"Cache speedup: {duration / cached_duration:.2f}x")

if __name__ == "__main__":
    """Run all tests"""
    logger.info("Testing health endpoint...")
    test_health_endpoint()
    
    logger.info("\nTesting dashboard stats endpoint...")
    test_dashboard_stats()
    
    logger.info("\nTesting activity feed endpoint...")
    test_activity_feed()
    
    logger.info("\nTesting users endpoint...")
    test_users_endpoint()
    
    logger.info("\nAll tests completed!") 