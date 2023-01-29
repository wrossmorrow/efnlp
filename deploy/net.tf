
locals {
  nettags = {
    Name = "efnlp"
  }
}

data aws_availability_zones zones {
  state = "available"
}

# the VPC

resource aws_vpc vpc {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = local.nettags
}

# Internet gateway for the public subnet

resource aws_internet_gateway ig {
  vpc_id = aws_vpc.vpc.id
  tags = local.nettags
}

# Elastic IP for NAT

resource aws_eip nat {
  vpc        = true
  depends_on = [aws_internet_gateway.ig]
  tags = local.nettags
}

# NAT

resource aws_nat_gateway nat {
  allocation_id = aws_eip.nat.id
  subnet_id     = element(aws_subnet.public.*.id, 0)
  depends_on    = [aws_internet_gateway.ig]
  tags = local.nettags
}

# Public subnet

resource aws_subnet public {
  count                   = length(var.public_subnets_cidr)
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = element(var.public_subnets_cidr, count.index)
  availability_zone       = element(var.availability_zones, count.index)
  map_public_ip_on_launch = true
  tags = local.nettags
}

# Private subnet

resource aws_subnet private {
  count                   = length(var.private_subnets_cidr)
  vpc_id                  = aws_vpc.vpc.id
  cidr_block              = element(var.private_subnets_cidr, count.index)
  availability_zone       = element(var.availability_zones, count.index)
  map_public_ip_on_launch = false
  tags = local.nettags
}

# Routing tables

resource aws_route_table public {
  vpc_id = aws_vpc.vpc.id
  tags = local.nettags
}

resource aws_route_table private {
  vpc_id = aws_vpc.vpc.id
  tags = local.nettags
}

resource aws_route public_ig {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.ig.id
}

resource aws_route private_nat {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat.id
}

resource aws_route_table_association public {
  count          = "${length(var.public_subnets_cidr)}"
  subnet_id      = "${element(aws_subnet.public.*.id, count.index)}"
  route_table_id = aws_route_table.public.id
}

resource aws_route_table_association private {
  count          = length(var.private_subnets_cidr)
  subnet_id      = element(aws_subnet.private.*.id, count.index)
  route_table_id = aws_route_table.private.id
}

# Security groups

resource aws_security_group default {
  name        = "efnlp-default"
  description = "Default security group to allow inbound/outbound from the VPC"
  vpc_id      = aws_vpc.vpc.id

  ingress {
    from_port = "0"
    to_port   = "0"
    protocol  = "-1"
    self      = true
  }
  
  egress {
    from_port = "0"
    to_port   = "0"
    protocol  = "-1"
    self      = "true"
  }

  tags = local.nettags
}
