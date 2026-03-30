output "invoke_arn" {
  value = aws_lambda_function.api_handler.invoke_arn
}

output "function_name" {
  value = aws_lambda_function.api_handler.function_name
}