data "aws_key_pair" "ec2Key" {
  key_name = "ec2aws"

}

data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  owners = ["099720109477"] # Canonical

}

data "aws_vpc" "default" {
  default = true
}

resource "aws_iam_role" "firecraker" {
  name = "firecraker-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "firecraker_rootfs" {
  name = "firecraker-rootfs-s3-access"
  role = aws_iam_role.firecraker.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "arn:aws:s3:::firecracker-rootfs-bucket/firecracker/rootfs/node-agent-rootfs.ext4.zst"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "firecraker" {
  name = "firecraker-ec2-profile"
  role = aws_iam_role.firecraker.name
}

resource "aws_security_group" "firecraker" {
  name   = "Firecrake security group"
  vpc_id = data.aws_vpc.default.id

}

resource "aws_vpc_security_group_ingress_rule" "allow_ip4" {
  security_group_id = aws_security_group.firecraker.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 22
  ip_protocol       = "tcp"
  to_port           = 22
}

resource "aws_vpc_security_group_ingress_rule" "allow_app_ip4" {
  security_group_id = aws_security_group.firecraker.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 8000
  ip_protocol       = "tcp"
  to_port           = 8000
}

resource "aws_vpc_security_group_egress_rule" "allow_all_out" {
  security_group_id = aws_security_group.firecraker.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_instance" "firecraker" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "m8i.large"
  instance_market_options {
    market_type = "spot"
  }

  security_groups             = [aws_security_group.firecraker.name]
  associate_public_ip_address = true
  key_name                    = data.aws_key_pair.ec2Key.key_name
  iam_instance_profile        = aws_iam_instance_profile.firecraker.name

  cpu_options {
    nested_virtualization = "enabled"
  }

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
  }

  user_data = file("${path.module}/init.sh")

  tags = {
    Name = "Firecraker...."
  }
}