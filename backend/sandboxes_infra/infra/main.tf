terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = "~> 4.0"
        }
    }
    required_version = ">= 1.15.0"
}

provider "aws" {
    region = var.aws_region
}

module "ec2"{
    source = "./modules/ec2"

}


variable "aws_region" {
    type = string
    default = "us-east-1"
}
