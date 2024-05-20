import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
def select_vpc(vpcs):
    print("Available VPCs:")
    for index, vpc in enumerate(vpcs, start=1):
        print(f"{index}. VPC ID: {vpc['VpcId']}")
    while True:
        try:
            choice = int(input("Enter the number corresponding to the VPC you want to replicate: "))
            if 1 <= choice <= len(vpcs):
                return vpcs[choice - 1]['VpcId']
            else:
                print("Invalid choice. Please enter a valid number.")
        except ValueError:
            print("Invalid input. Please enter a number.")
def get_vpcs(ec2_client):
    try:
        response = ec2_client.describe_vpcs()
        return response['Vpcs']
    except ClientError as e:
        print(f"Failed to describe VPCs: {e}")
        return []
def get_vpc_subnet_info(ec2_client, vpc_id):
    try:
        vpcs = ec2_client.describe_vpcs(VpcIds=[vpc_id])['Vpcs']
        if not vpcs:
            print("VPC not found in the source region.")
            return None, None, None
        subnets = ec2_client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['Subnets']
        if not subnets:
            print("No subnets found in the source VPC.")
            return None, None, None
        igws = ec2_client.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}])['InternetGateways']
    except ClientError as e:
        print(f"Failed to describe resources: {e}")
        return None, None, None
    vpc = vpcs[0]
    public_subnets = []
    private_subnets = []
    for subnet in subnets:
        try:
            route_tables = ec2_client.describe_route_tables(Filters=[{'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}])['RouteTables']
            is_public = any(
                'GatewayId' in route and route['GatewayId'].startswith('igw-') for route_table in route_tables for route in route_table['Routes']
            )
            if is_public:
                public_subnets.append(subnet)
            else:
                private_subnets.append(subnet)
        except ClientError as e:
            print(f"Failed to describe route tables for subnet {subnet['SubnetId']}: {e}")
    return vpc, public_subnets, private_subnets
def create_vpc(ec2_client, cidr_block):
    try:
        response = ec2_client.create_vpc(CidrBlock=cidr_block)
        vpc = response['Vpc']
        ec2_client.create_tags(Resources=[vpc['VpcId']], Tags=[{'Key': 'Name', 'Value': 'MyVPC'}])
        print(f"Created VPC with ID: {vpc['VpcId']}")
        return vpc['VpcId']
    except ClientError as e:
        print(f"Failed to create VPC: {e}")
        return None
def create_subnet(ec2_client, vpc_id, cidr_block, availability_zone):
    try:
        response = ec2_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr_block,
            AvailabilityZone=availability_zone
        )
        subnet = response['Subnet']
        print(f"Created subnet with ID: {subnet['SubnetId']} in availability zone: {availability_zone}")
        return subnet['SubnetId']
    except ClientError as e:
        print(f"Failed to create subnet: {e}")
        return None
def create_internet_gateway(ec2_client):
    try:
        response = ec2_client.create_internet_gateway()
        igw = response['InternetGateway']
        print(f"Created Internet Gateway with ID: {igw['InternetGatewayId']}")
        return igw['InternetGatewayId']
    except ClientError as e:
        print(f"Failed to create internet gateway: {e}")
        return None
def attach_internet_gateway(ec2_client, vpc_id, igw_id):
    try:
        ec2_client.attach_internet_gateway(VpcId=vpc_id, InternetGatewayId=igw_id)
        print(f"Attached Internet Gateway with ID: {igw_id} to VPC with ID: {vpc_id}")
    except ClientError as e:
        print(f"Failed to attach internet gateway: {e}")
def create_route_table(ec2_client, vpc_id):
    try:
        response = ec2_client.create_route_table(VpcId=vpc_id)
        rt = response['RouteTable']
        print(f"Created Route Table with ID: {rt['RouteTableId']}")
        return rt['RouteTableId']
    except ClientError as e:
        print(f"Failed to create route table: {e}")
        return None
def create_route(ec2_client, rt_id, igw_id):
    try:
        ec2_client.create_route(RouteTableId=rt_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
        print(f"Created route in Route Table with ID: {rt_id} to Internet Gateway with ID: {igw_id}")
    except ClientError as e:
        print(f"Failed to create route: {e}")
def associate_route_table(ec2_client, rt_id, subnet_id):
    try:
        ec2_client.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
        print(f"Associated Route Table with ID: {rt_id} to Subnet with ID: {subnet_id}")
    except ClientError as e:
        print(f"Failed to associate route table: {e}")
def replicate_vpc_configuration(source_region, target_region, vpc_id):
    ec2_client_source = boto3.client('ec2', region_name=source_region)
    ec2_client_target = boto3.client('ec2', region_name=target_region)
    # Get VPC and subnet info from source region
    vpc_source, public_subnets_source, private_subnets_source = get_vpc_subnet_info(ec2_client_source, vpc_id)
    if not vpc_source or (not public_subnets_source and not private_subnets_source):
        print("Failed to fetch source VPC and subnets information.")
        return
    print(f"Source VPC ID: {vpc_source['VpcId']}, Public Subnets: {len(public_subnets_source)}, Private Subnets: {len(private_subnets_source)}")
    # Create VPC in target region
    vpc_id_target = create_vpc(ec2_client_target, vpc_source['CidrBlock'])
    if not vpc_id_target:
        print("Failed to create VPC in target region.")
        return
    print(f"Created VPC in {target_region} with ID {vpc_id_target}")
    # Create Internet Gateway and attach to VPC
    igw_id_target = create_internet_gateway(ec2_client_target)
    if not igw_id_target:
        print("Failed to create internet gateway in target region.")
        return
    attach_internet_gateway(ec2_client_target, vpc_id_target, igw_id_target)
    print(f"Created and attached Internet Gateway with ID {igw_id_target}")
    # Create Route Table and Route
    rt_id_target = create_route_table(ec2_client_target, vpc_id_target)
    if not rt_id_target:
        print("Failed to create route table in target region.")
        return
    create_route(ec2_client_target, rt_id_target, igw_id_target)
    print(f"Created Route Table with ID {rt_id_target} and added route to IGW")
    # Get availability zones in target region
    try:
        azs_target = ec2_client_target.describe_availability_zones()['AvailabilityZones']
        if len(azs_target) < 2:
            print("Not enough availability zones in target region.")
            return
        az1_target = azs_target[0]['ZoneName']
        az2_target = azs_target[1]['ZoneName']
    except ClientError as e:
        print(f"Failed to describe availability zones: {e}")
        return
    # Create subnets in target region
    public_subnet_ids = []
    private_subnet_ids = []
    for i, subnet in enumerate(public_subnets_source):
        az = az1_target if i % 2 == 0 else az2_target
        subnet_id = create_subnet(ec2_client_target, vpc_id_target, subnet['CidrBlock'], az)
        if subnet_id:
            associate_route_table(ec2_client_target, rt_id_target, subnet_id)
            public_subnet_ids.append(subnet_id)
            print(f"Created Public Subnet with ID {subnet_id} in {az}")
    for i, subnet in enumerate(private_subnets_source):
        az = az1_target if i % 2 == 0 else az2_target
        subnet_id = create_subnet(ec2_client_target, vpc_id_target, subnet['CidrBlock'], az)
        if subnet_id:
            private_subnet_ids.append(subnet_id)
            print(f"Created Private Subnet with ID {subnet_id} in {az}")
    return {
        'VPC': vpc_id_target,
        'PublicSubnets': public_subnet_ids,
        'PrivateSubnets': private_subnet_ids
    }
if __name__ == "__main__":
    try:
        source_region = input("Enter the source region: ")
        target_region = input("Enter the target region: ")
        ec2_client_source = boto3.client('ec2', region_name=source_region)
        vpcs = get_vpcs(ec2_client_source)
        if not vpcs:
            print("No VPCs found in the source region.")
            exit(1)
        selected_vpc_id = select_vpc(vpcs)
        print(f"Selected VPC ID: {selected_vpc_id}")
        vpc_config = replicate_vpc_configuration(source_region, target_region, selected_vpc_id)
        if vpc_config:
            print("VPC Configuration in target region:", vpc_config)
        else:
            print("Failed to replicate VPC configuration.")
    except (NoCredentialsError, PartialCredentialsError) as e:
        print(f"Credentials error: {e}")
    except ClientError as e:
        print(f"AWS Client error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")