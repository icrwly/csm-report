import sys
import requests
import subprocess
import json
import os
import statistics
from jinja2 import Template
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# Check if the organization ID is provided as a command-line argument
if len(sys.argv) != 2:
  print("Usage: python csm2.py <organization_id>")
  sys.exit(1)

org_id = sys.argv[1]

    # Session variable (cookie) value
session_cookie = f"X-Pantheon-Admin-Session=bfee453a-5bfd-4acd-9649-ac29d6155abb:3cd2d9fa-da47-11ee-ba44-6e0129d7002d:1V1NyCqiLo8c0bZOaQ1tC"

    # Construct headers dictionary with the session variable (cookie)
headers = {"Cookie": session_cookie}
 
    # Path to the client certificate file
cert_path = os.path.expanduser("~/certs/ian.crowley@getpantheon.com.pem")

    # Disable SSL certificate verification
requests.packages.urllib3.disable_warnings()  # Ignore SSL certificate warnings

def get_customer_info(account_id):
    print("get_customer_info")
    # API endpoint to fetch customer information
    customer_info_url = f"https://admin.dashboard.pantheon.io/api/accounts/{account_id}"
    response = requests.get(customer_info_url, cert=cert_path, headers=headers, verify=False)
    print(response)  
    if response.status_code == 200:
        customer_data = response.json()
        customer_name = customer_data["profile"]["name"]
        return customer_name
    else:
        print(f"Failed to fetch customer information for account ID {account_id}")
        return None

def get_account_tier(account_id):
    print("get_account_tier")
    # API endpoint to fetch account tier information
    account_tier_url = f"https://admin.dashboard.pantheon.io/api/accounts/{account_id}/tier"
    response = requests.get(account_tier_url, cert=cert_path, headers=headers, verify=False)
    if response.status_code == 200:
        tier_data = response.json()
        account_tier = tier_data["tier_name"]
        return account_tier
    else:
        print(f"Failed to fetch account tier information for account ID {account_id}")
        return None

# Get customer information
customer_name = get_customer_info(org_id)
print(customer_name)
if not customer_name:
    exit("Failed to retrieve customer information.")

# Get account tier
account_tier = get_account_tier(org_id)
if not account_tier:
    exit("Failed to retrieve account tier information.")

# Run Terminus command to get the team members
team_members_command = f'terminus org:people:list {org_id} --format json'
team_members_output = subprocess.getoutput(team_members_command)
team_members_data = json.loads(team_members_output)

# Filter team members with @getpantheon.com email address
pantheon_team_members = {user_id: user_info for user_id, user_info in team_members_data.items() if not user_info.get("email", "").endswith("@getpantheon.com")}

# Function to check certification status
def is_certified(email):
    print("get certifed")
    certification_api_url = f'https://certification.pantheon.io/api/v1/certification-list?email={email}'
    response = requests.get(certification_api_url)
    return bool(response.json())

# Function to check support ticket volume 

def get_ticket_volume(org_id, days=30, admin_cookie=''):
    print("get_ticket_volume")
    # Calculate the date from 30 days ago
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Session variable (cookie) value
    session_cookie = f"X-Pantheon-Admin-Session={admin_cookie}"

    # Construct headers dictionary with the session variable (cookie)
    headers = {"Cookie": session_cookie}
 
    # Path to the client certificate file
    cert_path = os.path.expanduser("~/certs/ian.crowley@getpantheon.com.pem")

    # Disable SSL certificate verification
    requests.packages.urllib3.disable_warnings()  # Ignore SSL certificate warnings

    # Make API request to get tickets with headers and SSL cert verification disabled
    ticket_api_url = f'https://admin.dashboard.pantheon.io/api/accounts/{org_id}/tickets'
    # print(ticket_api_url)
    response = requests.get(ticket_api_url, cert=cert_path, headers=headers, verify=False)
    
    if response.status_code == 200:
        tickets_data = response.json()

        # Filter tickets created in the last 30 days
        recent_tickets = [ticket for ticket in tickets_data if ticket.get("created_at") >= start_date]

        # Count tickets based on status
        created_count = len(recent_tickets)
        closed_count = sum(1 for ticket in recent_tickets if ticket.get("status") == "solved")
        open_count = created_count - closed_count

        return created_count, closed_count, open_count
    else:
        print(f"Failed to fetch ticket data. Status code: {response.status_code}")
        return None, None, None
    
# Run Terminus command to check Custom Upstreams
custom_upstreams_command = f'terminus org:upstream:list {org_id} --format=json'
custom_upstreams_output = subprocess.getoutput(custom_upstreams_command)

# Check if the output contains the warning message indicating no upstreams
if "[warning] You have no upstreams." in custom_upstreams_output:
    custom_upstreams_status = "No"
else:
    custom_upstreams_status = "Yes"

print("Custom Upstreams:", custom_upstreams_status)

# Function to check caching status and cache hit ratio for a given domain
def check_caching(site_name, threshold=60, output_file="caching-below60-report.txt"):
    try:
        # Run Terminus command to get website metrics
        terminus_command = f"terminus env:metrics {site_name}.live --format=json"
        response = subprocess.getoutput(terminus_command)
        
        # Parse the JSON response
        data = json.loads(response)
        
        # Extract cache hit ratios
        cache_hit_ratios = [float(entry['cache_hit_ratio'][:-1]) for entry in data['timeseries'].values() if entry['cache_hit_ratio'] != "--"]
        # Calculate the average cache hit ratio
        average_cache_hit_ratio = sum(cache_hit_ratios) / len(cache_hit_ratios)

        # Check if the average cache hit ratio is below the threshold
        if average_cache_hit_ratio < threshold:
            # Open the output file in append mode
            with open(output_file, "a") as file:
                # Write the site name and its cache hit ratio to the file
                file.write(f"{site_name}: {average_cache_hit_ratio:.2f}\n")
            return True
        else:
            return False
    
    except Exception as e:
        print(f"Error: {e}")
        return False

def get_redis_command(site_name):
    """
    Fetches the Redis command to connect to a site's live instance using Terminus.

    Args:
        site_name (str): The name of the site.

    Returns:
        str: The Redis command if Redis is enabled, otherwise None.
    """
    command = f"terminus connection:info {site_name}.live --fields=redis_command --format json"
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        # If data is a dictionary, directly extract the Redis command
        if isinstance(data, dict):
            redis_command = data.get("redis_command")
            if not redis_command:
                print(f"Redis is not enabled for {site_name}.")
                return None
            return redis_command
        # If data is a list of dictionaries or strings
        elif isinstance(data, list):
            for connection in data:
                # Check if data is a dictionary
                if isinstance(connection, dict):
                    redis_command = connection.get("redis_command")
                    if redis_command:
                        return redis_command
                # Check if data is a string
                elif isinstance(connection, str):
                    if connection:
                        return connection
            print(f"No Redis command found for {site_name}.")
            return None
        else:
            print(f"Unexpected data format: {data}")
            return None
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error getting Redis command: {e}")
        return None

def check_redis_status(redis_command):
    """
    Checks if Redis is enabled and configured properly by connecting to the Redis server and running DBSIZE command.

    Args:
        redis_command (str): The Redis command.

    Returns:
        bool: True if Redis is enabled and configured properly, False otherwise.
    """
    if not redis_command:
        return False
    
    command = f"{redis_command} DBSIZE"
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        dbsize = int(result.stdout.strip().split()[-1])
        print(f"Redis DBSIZE: {dbsize}")
        return dbsize > 0
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error checking Redis status: {e}")
        return False
    
# Run Terminus command to get the list of sites
terminus_command = f'terminus org:site:list {org_id} --format=json'
print("get site list")
raw_output = subprocess.check_output(terminus_command, shell=True, text=True)
sites_data = json.loads(raw_output)

# Filter out sandbox sites
non_sandbox_sites = [site for site in sites_data.values() if site.get("plan_name") != "Sandbox"]
D7sites = [site for site in sites_data.values() if site.get("framework") == "drupal" ]
total_sites = len(non_sandbox_sites)
total_D7_sites = len(D7sites)
print(total_D7_sites)

# Initialize counters for metrics
multidev_sites_count = 0
wordpress_sites_count = 0
drupal_sites_count = 0
autopilot_sites_count = 0
quicksilver_hooks_sites_count = 0
build_tools_sites_count = 0
agcdn_enabled_sites_count = 0
total_sites_with_primary_domain = 0
total_sites_with_caching_below_60 = 0
redis_enabled_sites_count = 0

# List to store sites not using AGCDN
sites_not_using_agcdn = []

def perform_site_checks(site_info):
    global multidev_sites_count
    global wordpress_sites_count
    global drupal_sites_count
    global autopilot_sites_count
    global quicksilver_hooks_sites_count
    global build_tools_sites_count
    global agcdn_enabled_sites_count
    global total_sites_with_primary_domain
    global total_sites_with_caching_below_60
    global redis_enabled_sites_count
    # Get the site name
    site_name = site_info["name"]
    # Run Terminus command to get the primary domain
    primary_domain_command = f'terminus domain:list {site_name}.live --format=json'
    primary_domain_output = subprocess.getoutput(primary_domain_command)

    try:
        primary_domain_data = json.loads(primary_domain_output)
        # Find the primary domain
        primary_domain = next((domain for domain, info in primary_domain_data.items() if info.get("primary")), None)
      
        if primary_domain:
            # Increment the counter for sites with a primary domain
            total_sites_with_primary_domain += 1

            # Run cURL command to check AGCDN status on the primary domain
            agcdn_check_command = f'curl https://{primary_domain} -H "pantheon-debug: 1" -s -D - -o /dev/null'
            agcdn_check_output = subprocess.getoutput(agcdn_check_command)
            
            # Check if AGCDN is enabled
            if "agcdn-info" in agcdn_check_output:
                agcdn_enabled_sites_count += 1
            else:
                sites_not_using_agcdn.append(site_name)
            
            # Check caching status
            if check_caching(site_name):
                total_sites_with_caching_below_60 += 1

            # Check Redis status
            redis_command = get_redis_command(site_name)
            
            if redis_command:
                if check_redis_status(redis_command):
                    print("Redis is enabled and configured properly.")
                    redis_enabled_sites_count += 1
                else:
                    print("Redis is enabled but may not be configured properly.")
                    redis_enabled_sites_count += 1
            else:
                print("Redis is not enabled.")

    except json.JSONDecodeError:
        print(f"Error decoding JSON for primary domain of {site_name}")

    # Run Terminus command to get the list of multidev environments
    multidev_command = f'terminus multidev:list {site_name} --format=json'
    multidev_output = subprocess.getoutput(multidev_command)

    # Check if the output contains multidev environments
    if "You have no multidev environments" not in multidev_output:
        multidev_sites_count += 1

    # Check the framework of the site
    if "wordpress" in site_info.get("framework", "").lower():
        wordpress_sites_count += 1
    elif "drupal" in site_info.get("framework", "").lower():
        drupal_sites_count += 1

    # Run Terminus command to check Autopilot status
    autopilot_command = f'terminus site:autopilot:frequency {site_name}'
    autopilot_output = subprocess.getoutput(autopilot_command)

    # Check if Autopilot is enabled
    if autopilot_output.find('[error]') == -1:
        autopilot_sites_count += 1

    # Run Terminus command to check Quicksilver Hooks
    quicksilver_hooks_command = f'terminus workflow:info:logs {site_name}'
    quicksilver_hooks_output = subprocess.getoutput(quicksilver_hooks_command)

    # Check if Quicksilver Hooks are present
    if "[notice] Workflow operations did not contain any logs" not in quicksilver_hooks_output:
        quicksilver_hooks_sites_count += 1

    # Run Terminus command to check Build Tools
    build_tools_command = f'terminus build:project:info {site_name}'
    build_tools_output = subprocess.getoutput(build_tools_command)

    # Check if Build Tools are present
    if "[error]" not in build_tools_output:
        build_tools_sites_count += 1

    
# Function to process sites concurrently
def process_sites_concurrently(sites):
    with ThreadPoolExecutor() as executor:
        # Submit each site for processing concurrently
        futures = [executor.submit(perform_site_checks, site) for site in sites]
        # Wait for all tasks to complete
        for future in futures:
            future.result()  # This waits for the task to complete and retrieves its result if any

# Call the function to process sites concurrently
process_sites_concurrently(non_sandbox_sites)

# Calculate percentages
percentage_multidev_sites = round((multidev_sites_count / total_sites) * 100)
percentage_wordpress_sites = round((wordpress_sites_count / total_sites) * 100)
percentage_drupal_sites = round((drupal_sites_count / total_sites) * 100)
percentage_autopilot_sites = round((autopilot_sites_count / total_sites) * 100)
percentage_quicksilver_hooks_sites = round((quicksilver_hooks_sites_count / total_sites) * 100)
percentage_build_tools_sites = round((build_tools_sites_count / total_sites) * 100)
percentage_agcdn_enabled_sites = round((agcdn_enabled_sites_count / total_sites_with_primary_domain) * 100)
percentage_sites_with_caching = round((total_sites_with_caching_below_60 / total_sites_with_primary_domain) * 100)
percentage_redis_enabled = round((redis_enabled_sites_count / total_sites_with_primary_domain) * 100)

# Get ticket volume
created_count, closed_count, open_count = get_ticket_volume(org_id, days=30, admin_cookie="bfee453a-5bfd-4acd-9649-ac29d6155abb:cfd7ee7c-db17-11ee-96c7-56080d6812bb:ZShoOLScVV5xfcU2dlkhf")

# HTML template
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Pantheon Report</title>
  <!-- Include Tailwind CSS CDN or link to your local file -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css">
  <style>

  ul.flex li:not(:last-child)::after {
    content: "|";
    margin-left: 5px;
    margin-right: 5px;
  }

  </style>
</head>
<body class="font-sans bg-gradient-to-tr from-black via-indigo-800 to-yellow-300 h-screen p-8">

  <h1 class="text-4xl text-white font-bold mb-8">Pantheon Customer Report - {{ customer_name }} ({{ account_tier }})</h1>

  <section class="bg-white rounded-md p-6 mb-8">
    <h2 class="text-2xl font-bold mb-4">Total Number of Sites (Excluding Sandbox)</h2>
    <p>Total: {{ total_sites }}</p>
  </section>

    <section class="bg-white rounded-md p-6 mb-8">
     <h2 class="text-2xl font-bold mb-4">Team Members</h2>
     <table class="w-full">
      <thead>
        <tr>
          <th class="px-4 py-2 text-left">Email</th>
          <th class="px-4 py-2 text-left">Role</th>
          <th class="px-4 py-2 text-center">Certification</th>
        </tr>
      </thead>
      <tbody>
    
      {% for user_id, user_info in pantheon_team_members.items() %}
        <tr class="border-t border-gray-200">
          <td class="px-4 py-2">{{ user_info["email"] }}</td> 
          <td class="px-4 py-2">{{ user_info["role"] }}</td>
          <td class="px-4 py-2 text-center">{% if is_certified(user_info["email"]) %}Yes{% else %}No{% endif %}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>

  <section class="bg-white rounded-md p-6 mb-8">
    <h2 class="text-2xl font-bold mb-4">CMS Frameworks</h2>
    <p>Percentage of sites using WordPress: {{ percentage_wordpress_sites }}%</p>
    <p>Percentage of sites using Drupal: {{ percentage_drupal_sites }}%</p>
    <p>{{ total_D7_sites }} sites are Drupal 7.  Drupal 7 end-of-life is January 5th, 2025</p>
  </section>

  <section class="bg-white rounded-md p-6 mb-8">
    <h2 class="text-2xl font-bold mb-4">WebOps Adoption Metrics</h2>
    <p>Percentage of sites with one or more Multidev environments: {{ percentage_multidev_sites }}%</p>
    <p>Percentage of sites using Autopilot: {{ percentage_autopilot_sites }}%</p>
    <p>Percentage of sites using Quicksilver Hooks: {{ percentage_quicksilver_hooks_sites }}%</p>
    <p>Percentage of sites using Build Tools: {{ percentage_build_tools_sites }}%</p>
    <p>Using Custom Upstreams: {{ custom_upstreams_status }}</p>  
  </section>

  <section class="bg-white rounded-md p-6 mb-8">
    <h2 class="text-2xl font-bold mb-4">AGCDN Usage</h2>
    <p>Percentage of sites where AGCDN is enabled: {{ percentage_agcdn_enabled_sites }}%</p>
    {% if sites_not_using_agcdn and (percentage_agcdn_enabled_sites != 0 and percentage_agcdn_enabled_sites != 100) %}
    <p>Sites not using AGCDN:</p>
    <ul class="flex flex-wrap items-left justify-left text-gray-900 dark:text-white">
      {% for site in sites_not_using_agcdn %}
        <li>{{ site }}</li>
      {% endfor %}
    </ul>
    {% endif %}
  </section>

  <section class="bg-white rounded-md p-6 mb-8">
    <h2 class="text-2xl font-bold mb-4">Caching Best Practices</h2>
    <p>Percentage of sites with a CHR below 60: {{ total_sites_with_caching_below_60 }}%</p>
    <p>Percentage of sites with Redis enabled: {{ percentage_redis_enabled }}%</p>
    {% if total_sites_with_caching_below_60 != 0 %}
    <p><a href="caching-below60-report.txt">Caching Report</p>
    {% endif %}
  </section>

  <section class="bg-white rounded-md p-6 mb-8">
    <h2 class="text-2xl font-bold mb-4">Support Ticket Volume (Last 30 days)</h2>
    <p>Total tickets created: {{ created_count }}</p>
    <p>Tickets closed: {{ closed_count }}</p>
    <p>Tickets open: {{ open_count }}</p>
  </section>

  <!-- Add more sections as needed -->

</body>
</html>
"""

# Render the HTML template
template = Template(html_template)
html_content = template.render(
    total_sites=total_sites,
    total_D7_sites=total_D7_sites,
    percentage_multidev_sites=percentage_multidev_sites,
    percentage_wordpress_sites=percentage_wordpress_sites,
    percentage_drupal_sites=percentage_drupal_sites,
    percentage_autopilot_sites=percentage_autopilot_sites,
    percentage_quicksilver_hooks_sites=percentage_quicksilver_hooks_sites,
    percentage_build_tools_sites=percentage_build_tools_sites,
    custom_upstreams_status=custom_upstreams_status,
    percentage_agcdn_enabled_sites=percentage_agcdn_enabled_sites,
    sites_not_using_agcdn=sites_not_using_agcdn,
    pantheon_team_members=pantheon_team_members,
    is_certified=is_certified,
    created_count=created_count,
    closed_count=closed_count,
    open_count=open_count,
    total_sites_with_caching_below_60=total_sites_with_caching_below_60,
    percentage_redis_enabled=percentage_redis_enabled,
    customer_name=customer_name,
    account_tier=account_tier

)

# Write HTML content to a file
with open("pantheon_site_report.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Report generated successfully.")
