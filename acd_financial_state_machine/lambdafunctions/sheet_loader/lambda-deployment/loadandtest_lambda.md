# Deploy the updated function
zip -r lambda-deployment-fixed.zip .
aws lambda update-function-code \
    --function-name sheet_loader \
    --zip-file fileb://lambda-deployment-fixed.zip

# Test the function
aws lambda invoke \
    --function-name sheet_loader \
    --payload file://test-event.json \
    response.json

cat response.json