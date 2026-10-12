import io
from flask import Flask, Response
from basyx.aas.adapter.aasx import AASXReader, DictSupplementaryFileContainer
from basyx.aas.model import DictIdentifiableStore
from basyx.aas.adapter.json import write_aas_json_file

app = Flask(__name__)

# Initialize memory stores for the digital twins and any attached files
object_store = DictIdentifiableStore()
file_store = DictSupplementaryFileContainer()

# Extract the AASX package and load the machines into memory
with AASXReader("AI4I_fleet.aasx") as reader:
    reader.read_into(object_store, file_store)

# Define the standard Industry 4.0 API endpoint
@app.route('/api/v3.0/shells', methods=['GET'])
def get_shells():
    # Serialize the in-memory AAS objects to JSON format
    json_buffer = io.StringIO()
    write_aas_json_file(json_buffer, object_store)
    
    # Serve the data over the network
    return Response(json_buffer.getvalue(), mimetype='application/json')

if __name__ == '__main__':
    print("AAS REST Server starting on port 8080...")
    app.run(host='0.0.0.0', port=8080)