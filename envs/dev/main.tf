provider "aws" {
  region = "eu-central-1"
}

locals {
  prefix = "vyshynska-nataliia-03"
}

module "database" {
  source     = "../../modules/dynamodb"
  table_name = "${local.prefix}-links-table"
}

module "backend" {
  source              = "../../modules/lambda"
  function_name       = "${local.prefix}-links-handler"
  source_file         = "${path.root}/../../src/app.py"
  dynamodb_table_arn  = module.database.table_arn
  dynamodb_table_name = module.database.table_name
}

module "api" {
  source               = "../../modules/api_gateway"
  api_name             = "${local.prefix}-links-api"
  lambda_invoke_arn    = module.backend.invoke_arn
  lambda_function_name = module.backend.function_name
}