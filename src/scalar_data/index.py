import os
import urllib3

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

urllib3.disable_warnings()

logger = Logger()
tracer = Tracer()

# Vendia Share node data
share_node_url = os.getenv('SHARE_NODE_URL')
share_node_api_key = os.getenv('SHARE_NODE_API_KEY')

transport=RequestsHTTPTransport(
    url=share_node_url,
    use_json=True,
    headers={
        "Content-type": "application/json",
        "x-api-key": share_node_api_key
    },
    verify=False,
    retries=3,
)

gql_client = Client(
    transport=transport,
    fetch_schema_from_transport=True,
)


def add_to_share(email, image, last_updated, status, first_dose, second_dose):
    '''Add selected vaccine record data to Vendia Share node

    Parameters
    ----------
    email: string, required
    image: string, required
    lastUpdated: number, required
    status: string, required
    first_dose: dict, required
    second_dose: dict, required

    Returns
    -------
    result: dict
        Result of the GraphQL mutation
    '''
    params = {
        "email": email,
        "image": image,
        "lastUpdated": last_updated,
        "status": status,
        "firstDose": first_dose,
        "secondDose": second_dose
    }

    insert_query = gql(
        """
        mutation addRecord(
            $email: String!,
            $image: String,
            $lastUpdated: String,
            $status: String,
            $firstDose: firstDoseInput,
            $secondDose: secondDoseInput
        ) {
            addVaccineRecord_async(
                input: {
                    email: $email,
                    image: $image,
                    lastUpdated: $lastUpdated,
                    status: $status,
                    firstDose: $firstDose,
                    secondDose: $secondDose
                }
            ) {
                error
                result {
                    id
                    node_owner
                    submission_time
                    tx_id
                }
            }
        }
        """
    )

    try:
        result = gql_client.execute(
            insert_query,
            variable_values=params
        )
    except Exception as e:
        raise Exception(f'Error: {str(e)}')

    return(result)


def remove_from_share(email):
    '''Remove vaccine record data from Vendia Share node

    Parameters
    ----------
    email: string, required

    Returns
    -------
    result: dict
        Result of the GraphQL query operation
    '''
    # Determine the Vendia id of the item_number
    params = {
        "email": email
    }

    search_query = gql(
        """
        query listVaccineRecord(
            $email: String!
        ) {
            listVaccineRecords(
                filter: {
                    email: {
                        eq: $email
                    }
                }
            ) {
                VaccineRecords {
                    id
                }
            }
        }
        """
    )

    try:
        result = gql_client.execute(
            search_query,
            variable_values=params
        )
    except Exception as e:
        raise Exception(f'Error: {str(e)}')
    
    record_id = result['listVaccineRecords']['VaccineRecords'][0]['id']

    # Remove the item from Vendia Share
    params = {
        "id": record_id
    }

    remove_query = gql(
        """
        mutation removeRecord(
            $id: ID!
        ) {
            removeVaccineRecord_async(
                id: $id
            ) {
                error
                result {
                    id
                }
            }
        }
        """
    )

    try:
        result = gql_client.execute(
            remove_query,
            variable_values=params
        )
    except Exception as e:
        raise Exception(f'Error: {str(e)}')

    return(result)


def update_in_share(email, image, last_updated, status, first_dose, second_dose):
    '''Update vaccine record data to Vendia Share node

    Parameters
    ----------
    email: string, required
    image: string, required
    lastUpdated: number, required
    status: string, required
    first_dose: dict, required
    second_dose: dict, required

    Returns
    -------
    result: dict
        Result of the GraphQL mutation
    '''
    # Determine the Vendia id of the email
    params = {
        "email": email
    }

    search_query = gql(
        """
        query listVaccineRecord(
            $email: String!
        ) {
            listVaccineRecords(
                filter: {
                    email: {
                        eq: $email
                    }
                }
            ) {
                VaccineRecords {
                    id
                }
            }
        }
        """
    )

    try:
        result = gql_client.execute(
            search_query,
            variable_values=params
        )
    except Exception as e:
        raise Exception(f'Error: {str(e)}')
    
    record_id = result['listVaccineRecords']['VaccineRecords'][0]['id']

    # Update the item in Vendia Share
    params = {
        "id": record_id,
        "email": email,
        "image": image,
        "lastUpdated": last_updated,
        "status": status,
        "firstDose": first_dose,
        "secondDose": second_dose
    }

    update_query = gql(
        """
        mutation updateVaccineRecord(
            $id: ID!,
            $email: String!,
            $image: String,
            $lastUpdated: String,
            $status: String,
            $firstDose: firstDoseInput,
            $secondDose: secondDoseInput
        ) {
            putVaccineRecord_async(
                id: $id,
                input: {
                    email: $email,
                    image: $image,
                    lastUpdated: $lastUpdated,
                    status: $status,
                    firstDose: $firstDose,
                    secondDose: $secondDose
                }
            ) {
                error
                result {
                    id
                }
            }
        }
        """
    )

    try:
        result = gql_client.execute(
            update_query,
            variable_values=params
        )
    except Exception as e:
        raise Exception(f'Error: {str(e)}')

    return(result)


@tracer.capture_method
@logger.inject_lambda_context
def handler(event, context):
    logger.info(event)
    for record in event['Records']:
        event_name = record["eventName"]

        if event_name == 'INSERT':
            new_image = record['dynamodb']['NewImage']

            # Determine whether the first dose has been added in Dynamo.
            # If it has, extract the values in the new image.
            first_dose=new_image.get("firstDose")
            f = {}
            if first_dose:
                f["manufacturer"] = new_image["firstDose"]["M"]["manufacturer"]["S"]
                f["lotNumber"] = new_image["firstDose"]["M"]["lotNumber"]["S"]
                f["administeredBy"] = new_image["firstDose"]["M"]["administeredBy"]["S"]
                f["administrationDate"] = new_image["firstDose"]["M"]["administrationDate"]["S"]

            # Determine whether the second dose has been added in Dynamo.
            # If it has, extract the values in the new image.        
            second_dose=new_image.get("secondDose")
            s = {}
            if second_dose:
                s["manufacturer"] = new_image["secondDose"]["M"]["manufacturer"]["S"]
                s["lotNumber"] = new_image["secondDose"]["M"]["lotNumber"]["S"]
                s["administeredBy"] = new_image["secondDose"]["M"]["administeredBy"]["S"]
                s["administrationDate"] = new_image["secondDose"]["M"]["administrationDate"]["S"]

            result = add_to_share(
                email=new_image["email"]["S"],
                image=new_image["image"]["S"],
                status=new_image["status"]["S"],
                last_updated=new_image["lastUpdated"]["S"],
                first_dose=f,
                second_dose=s
            )
        elif event_name == 'REMOVE':
            result = remove_from_share(
                email=record['dynamodb']['Keys']['email']['S']
            )
        elif event_name == 'MODIFY':
            new_image = record['dynamodb']['NewImage']

            # Determine whether the first dose has been added in Dynamo.
            # If it has, extract the values in the new image.
            first_dose=new_image.get("firstDose")
            f = {}
            if first_dose:
                f["manufacturer"] = new_image["firstDose"]["M"]["manufacturer"]["S"]
                f["lotNumber"] = new_image["firstDose"]["M"]["lotNumber"]["S"]
                f["administeredBy"] = new_image["firstDose"]["M"]["administeredBy"]["S"]
                f["administrationDate"] = new_image["firstDose"]["M"]["administrationDate"]["S"]

            # Determine whether the second dose has been added in Dynamo.
            # If it has, extract the values in the new image.        
            second_dose=new_image.get("secondDose")
            s = {}
            if second_dose:
                s["manufacturer"] = new_image["secondDose"]["M"]["manufacturer"]["S"]
                s["lotNumber"] = new_image["secondDose"]["M"]["lotNumber"]["S"]
                s["administeredBy"] = new_image["secondDose"]["M"]["administeredBy"]["S"]
                s["administrationDate"] = new_image["secondDose"]["M"]["administrationDate"]["S"]
            
            result = update_in_share(
                email=new_image["email"]["S"],
                image=new_image["image"]["S"],
                status=new_image["status"]["S"],
                last_updated=new_image["lastUpdated"]["S"],
                first_dose=f,
                second_dose=s
            )
        else:
            logger.error(f"We don't handle {event_name} yet")
        
        logger.info(result)
 