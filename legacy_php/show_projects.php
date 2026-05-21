<?php
    require('validate.php');
    $department = $_SESSION['department'];
    $authorization = $_SESSION['authorization'];
    $id = $_SESSION['id'];
    $department_code = $_SESSION['department_code'];
    $project_department = false;
    require('connection.php');
    // Check the connection
    if ($conn->connect_error) {
        die("Connection failed: " . $conn->connect_error);
    }
    $sql = "SELECT * FROM department where id=".$department_code." and project = 'Y'";
    $result = mysqli_query($conn, $sql);
    $sql = "SELECT * FROM employee where department = ".$department_code;
    $employee = mysqli_query($conn, $sql);
    if ($result && mysqli_num_rows($result) > 0) {
        $project_department = true;
    }
    if ($_SERVER["REQUEST_METHOD"] == "POST"){
        $comment = $_POST['comment'];
        $action1 = $_POST['action1'];
        $action2 = $_POST['action2'];
        $submit_id = $_POST['submit_id'];

        if ($action2 == 'Approve'){
            $action = "Y";
        }        
        if ($action2 == 'Reject'){
            $action = "R";
        }
        //approval level
        if(strpos($action1, "VP") !== false){ 
            $level = 1;
        }else{
            $level = 2;
        }
        //add assign to
        if ($action2 == 'Assign'){
            $type = 21;
            $action1 .= ": ";
            foreach ($_POST['assignment'] as $selected){
                $sql = 'SELECT short_name from employee WHERE id = ' .$selected;
                $result = mysqli_query($conn, $sql);
                $row = mysqli_fetch_array($result);
                $action1 .=  $row["short_name"].", ";
                $sql = "INSERT INTO project_assignment (assigned_by,assigned_to,project) VALUES (".$id.",".$selected.",".$submit_id.")";
                if ($conn->query($sql) === false) {
                    echo "Add assignment Error: " . $conn->error;
                    return;
                }
            }
            $action1 = substr($action1,0,-2);
            $status = 5;
        }else{
            $type = 19;
            $sql = 'SELECT * from approval WHERE project = ' .$submit_id." AND department = " .$department_code;
            //Add approval
            if (substr($action1,0,7) == 'Request'){           
                if(strpos($action1, "VP") !== false){ 
                    $approval_dept = $department_code;
                }else{
                    $sql = 'SELECT requestor_department as dept FROM projects WHERE id = ' .$submit_id;
                    $result = mysqli_query($conn, $sql);
                    if ($result && mysqli_num_rows($result) > 0){
                        $row = mysqli_fetch_array($result);
                        $approval_dept = $row["dept"];
                    }else{
                        echo "Check approval Error: " . $conn->error;
                    }
                }
                $sql = 'SELECT * from approval where project = ' .$submit_id. ' AND department = ' .$approval_dept.' AND access_level = '.$level;
                $result = mysqli_query($conn, $sql);
                if ($result && mysqli_num_rows($result) == 0) {
                    $sql = "INSERT INTO approval (department, access_level, status, project)
                            VALUES (".$approval_dept.",".$level.", 'N', ".$submit_id.")"; 
                    if ($conn->query($sql) === false) {
                        echo "Add approval request Error: " . $conn->error;
                        return;
                    }
                }  
                $status = 3;
            //Update approval
            }else{       
                $update = "UPDATE approval SET user=".$id.",date=now(),status='".$action."' WHERE project = " .$submit_id." AND user IS NULL AND department = " .$department_code;
                //check user access level
                if ($authorization > $level){
                    header('Location: error.php');    
                }           
            
                $sql .= " AND access_level = ".$level;
                $result = mysqli_query($conn, $sql);
                if ($result && mysqli_num_rows($result) > 0) {
                    $update .=  " AND access_level = ".$level;
                }                     

                if ($conn->query($update) === false) {
                    echo "Error updating approval record: " . $conn->error;
                }
                
                $sql = 'SELECT * from approval where project = ' .$submit_id.' AND user IS NULL'; //Check if the project gets all approved
                $result = mysqli_query($conn, $sql);   
                if ($action2 == 'Approve'){
                    if ($result && mysqli_num_rows($result) > 0) {
                        $status = 3;
                    }else{
                        $status = 4;
                    }
                }else{
                    $status = 10;
                }
            }
        }
        //Update project status
        $sql = "UPDATE projects SET status = ".$status.",last_act_date =now() WHERE id = " .$submit_id;   
        if ($conn->query($sql) === false) {
            echo "Error updating project status: " . $conn->error;
        }
        //Insert project log
        $sql = "INSERT INTO project_log (project, type, description, add_by)
                VALUES (".$submit_id.",".$type.",'".$action1."',".$id.")"; 
        if ($conn->query($sql) === false) {
            echo "Insert project log Error: " . $conn->error;
            return;
        }else{
            $log_id = $conn->insert_id;
        }
        if (!empty($comment)){
            //Insert possible comment for adding approval Request
            $sql = "INSERT INTO general_comment (user, subject_id, comment, subject)
                    VALUES (".$id.",".$log_id.", '".$comment."', 23)"; 
            if ($conn->query($sql) === false) {
                echo "Insert comment Error: " . $conn->error;
                return;
            }
        }
    }
    // Retrieve all project details from the database
    $sql = 'SELECT
            p.id,
            p.project_name,
            cast(p.date as date) as date,
            p.description,
            p.need_by_date,
            p.last_act_date,
            p.etd,
            e.short_name AS requestor,
            p.requestor as requestor_id,
            o.name AS status,
            oo.name AS type,
            d.name as department,
            d.id as department_code,
            p.project_department,
            dd.name as pd_name,
            IF(
                (
                SELECT
                    COUNT(*)
                FROM
                    approval ap
                LEFT JOIN employee ee ON
                    ee.id = ap.user
                WHERE
                    ap.project = p.id AND ap.department = p.project_department AND ap.access_level = 1
                ) = 0,
                \'N\',
                (
                SELECT
                    ee.name
                FROM
                    approval ap
                LEFT JOIN employee ee ON
                    ee.id = ap.user
                WHERE
                    ap.project = p.id AND ap.department = p.project_department AND ap.access_level = 1
                )
            ) AS mis_vp_approv,
            IF(
                (
                SELECT
                    COUNT(*)
                FROM
                    approval ap
                LEFT JOIN employee ee ON
                    ee.id = ap.user
                WHERE
                    ap.project = p.id AND ap.department = p.project_department AND ap.access_level = 2
                ) = 0,
                \'N\',
                (
                SELECT
                    ee.name
                FROM
                    approval ap
                LEFT JOIN employee ee ON
                    ee.id = ap.user
                WHERE
                    ap.project = p.id AND ap.department = p.project_department AND ap.access_level = 2
                )
            ) AS mis_approv,
            IF(
                (
                SELECT
                    COUNT(*)
                FROM
                    approval ap
                LEFT JOIN employee ee ON
                    ee.id = ap.user
                WHERE
                    ap.project = p.id AND ap.department = p.requestor_department AND ap.access_level = 2
            ) = 0,
            \'N\',
            (
            SELECT
                ee.name
            FROM
                approval ap
            LEFT JOIN employee ee ON
                ee.id = ap.user
            WHERE
                ap.project = p.id AND ap.department = p.requestor_department AND ap.access_level = 2
        )
            ) AS department_approv,
            ass.assign_to
        FROM
            projects p
        LEFT JOIN employee e ON
            p.requestor = e.id
        LEFT JOIN OPTIONS o ON
            p.status = o.id
        LEFT JOIN OPTIONS oo ON
            oo.id = p.type
        LEFT JOIN department d ON
            d.id = p.requestor_department
        LEFT JOIN department dd ON
            dd.id = p.project_department
        LEFT JOIN (
            SELECT GROUP_CONCAT(eee.short_name) as assign_to,pa.project
            FROM employee eee, project_assignment pa
            WHERE eee.id = pa.assigned_to
            GROUP BY pa.project
        ) ass ON 
        ass.project = p.id';

    if ($department == "Other" or ($authorization > 2 && $project_department = false)){
        $sql .= " WHERE p.requestor = '".$id."'";
    }else{
        $sql .= " WHERE p.requestor = ".$id." or (p.status NOT IN (10,11,8) and (p.requestor_department = ".$department_code." OR p.project_department = ".$department_code."))";
    }

    $result = $conn->query($sql);
    // Close the database connection
    $conn->close();
?>
<!DOCTYPE html>
<html>
<head>
  <title>Project Details</title>  
  
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.3.1/dist/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">  
  <link rel="stylesheet" href="style.css">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <?php    
    if ($authorization <= 2 or $project_department){
        echo "<h1>".$department." Department Projects</h1>";      
    ?>
        <div class="table-container" style="margin-bottom:50px">
            <table id="project-table" class="table_hover">
                <tr>
                    <th onclick="sortTable(0,this)">
                    Date
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(1,this)">
                    Project Name
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(2,this)">
                    Description
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(3,this)">
                    Department
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(4,this)">
                    Requestor
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(5,this)">
                    Status
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(6,this)">
                    Need By
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(7,this)">
                    Last Activity
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(8,this)">
                    Dept. Appro.
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(9,this)">
                    Proj. Dept.
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(10,this)">
                    Proj. Dept. Appro.
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(11,this)">
                    Proj. Dept. VP Appro.
                    <span class="sort-icon"></span>
                    </th>
                    <th onclick="sortTable(12,this)">
                    Assigned to
                    <span class="sort-icon"></span>
                    </th>                
                </tr>
    
                <?php
                $count = 0;
                $result->data_seek(0);
                if ($result && $result->num_rows > 0) {
                    // Output each project detail as a table row
                    while ($row = $result->fetch_assoc()) {
                        if ($row['requestor_id'] != $id){
                            echo '<tr>';
                            echo '<td>' . $row["date"] . '</td>';
                            echo '<td id="'.$row["id"].'"><a href="project_detail.php?id=' .$row["id"]. '" target="_blank">' . ucwords($row["project_name"]) . '</a></td>';                
                            echo '<td>' . $row["description"] . '</td>';
                            echo '<td>' . $row["department"] . '</td>';
                            echo '<td>' . $row["requestor"] . '</td>';
                            echo '<td>' . $row["status"] . '</td>';
                            echo '<td>' . $row["need_by_date"] . '</td>';
                            echo '<td><a href="#" onclick="window.open('."'".'project_log.php?i='.$row["id"]."',''".",'width=1200,height=600')".'";>' . $row["last_act_date"] . '</a></td>';
                            if ($row["department_approv"] == 'N'){
                                if ($department_code == $row["project_department"] && $row["project_department"] != $row["department_code"] && in_array($row["status"],array('Reviewing','Submitted'))){
                                    echo '<td><a type="button" class="btn btn-warning btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Request Department Approval" onclick="changeModalTitle(this)">
                                        Request Approval</a></td>';
                                }else{
                                    echo '<td>Not Required</td>';
                                }
                            }else{
                                if (is_null($row["department_approv"])){
                                    if ($row["department_code"] == $department_code && $authorization <=2 && $id != $row["requestor_id"]){
                                        echo '<td><button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Department Approval" onclick="changeModalTitle(this)">
                                            Approve</button>
                                        <button type="button" class="btn btn-danger btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Department Reject" onclick="changeModalTitle(this)">
                                            Reject</button></td>';
                                    }else{
                                        echo '<td>Pending</td>';
                                    }                       
                                }else{
                                    echo '<td>' . $row["department_approv"] . '</td>';
                                }   
                            }
                            echo '<td>' . $row["pd_name"] . '</td>';

                            if (is_null($row["mis_approv"])){
                                if ($department_code == $row["project_department"] && $authorization <=2){
                                    echo '<td><button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="' .$department. ' Approval" onclick="changeModalTitle(this)">
                                        Approve</button>
                                    <button type="button" class="btn btn-danger btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="' .$department. ' Reject" onclick="changeModalTitle(this)">
                                        Reject</button></td>';
                                }else{
                                    echo '<td>Pending</td>';
                                }                       
                            }else{
                                echo '<td>' . $row["mis_approv"] . '</td>';
                            }                       
                            
                            if ($row["mis_vp_approv"] == 'N'){
                                if ($department_code == $row["project_department"] && $authorization <=2 && in_array($row["status"],array('Reviewing','Submitted'))){
                                    echo '<td><button type="button" class="btn btn-warning btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Request ' .$department. ' VP Approval" onclick="changeModalTitle(this)">
                                        Request Approval</button></td>';
                                }else{
                                    echo '<td>Not Required</td>';
                                }             
                            }else{
                                if (is_null($row["mis_vp_approv"])){
                                    if ($department_code == $row["project_department"] && $authorization <=1 && $id != $row["requestor_id"]){
                                        echo '<td><button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="' .$department. ' VP Approval" onclick="changeModalTitle(this)">Approve</button>
                                        <button type="button" class="btn btn-danger btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="' .$department. ' VP Reject" onclick="changeModalTitle(this)">Reject</button></td>';
                                    }else{
                                        echo '<td>Pending</td>';
                                    }                        
                                }else{
                                    echo '<td>' . $row["mis_vp_approv"] . '</td>';
                                }   
                            }
                            if (is_null($row["assign_to"])){
                                if ($department_code == 1 && !is_null($row["mis_vp_approv"]) && !is_null($row["mis_approv"]) && !is_null($row["department_approv"])){
                                    if ($authorization <=2){
                                        echo '<td><button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Assign Employee" onclick="changeModalTitle(this)">Assign</button></td>';
                                    }else{
                                        echo '<td><button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Claim Project Ownership" onclick="changeModalTitle(this)">Claim</button></td>';
                                    }                     
                                }else{
                                    echo '<td>Not Assigned</td>';
                                }                        
                            }else{
                                echo '<td>' . $row["assign_to"] . '</td>';
                            }
                            echo '</tr>';
                            $count += 1;
                        }
                    }
                } else {
                        echo '<tr><td colspan="12">No project found.</td></tr>';
                }
                if ($count == 0){
                    echo '<tr><td colspan="12">No project found.</td></tr>';
                }
            ?>
    
            </table>
        </div>
    <?php
    }
    ?>
    <!--
    <h1>My Project Requests</h1>
    <div class="table-container" style="margin-bottom:50px">
        <table id="my-project-table" class="table_hover">
        <tr>
            <th onclick="sortTable(0,this)">
            Date
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(1,this)">
            Project Name
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(2,this)">
            Description
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(3,this)">
            Status
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(4,this)">
            Need By
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(5,this)">
            Dept. Appro.
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(6,this)">
            Proj. Dept.
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(7,this)">
            Proj. Dept. Appro.
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(8,this)">
            Proj. Dept. VP Appro.
            <span class="sort-icon"></span>
            </th>
            <th onclick="sortTable(9,this)">
            Assigned to
            <span class="sort-icon"></span>
            </th>                
        </tr>
    
        <?php
        if ($result && $result->num_rows > 0) {
            $count = 0;
            $result->data_seek(0);
            // Output each project detail as a table row
            while ($row = $result->fetch_assoc()) {
                if ($row['requestor_id'] == $id){
                    echo '<tr>';
                    echo '<td>' . $row["date"] . '</td>';
                    echo '<td id="'.$row["id"].'"><a href="project_detail.php?id=' . $row["id"] . '" target="_blank">' . ucwords($row["project_name"]) . '</a></td>';                
                    echo '<td>' . $row["description"] . '</td>';
                    echo '<td>' . $row["status"] . '</td>';
                    echo '<td>' . $row["need_by_date"] . '</td>';
                    if ($row["department_approv"] == 'N'){
                        echo '<td>Not Required</td>';
                    }else{
                        if (is_null($row["department_approv"])){
                            echo '<td>Pending</td>';
                        }else{
                            echo '<td>' . $row["department_approv"] . '</td>';
                        }   
                    }
                    echo '<td>' . $row["pd_name"] . '</td>';
                    if ($row["mis_approv"] == 'N' or $row["project_department"] == $department_code){
                        echo '<td>Not Required</td>';
                    }else{
                        if (is_null($row["mis_approv"])){
                            echo '<td>Pending</td>';
                        }else{
                            echo '<td>' . $row["mis_approv"] . '</td>';
                        }                       
                    }
                    if ($row["mis_vp_approv"] == 'N'){
                        echo '<td>Not Required</td>';
                    }else{
                        if (is_null($row["mis_vp_approv"])){
                            echo '<td>Pending</td>';
                        }else{
                            echo '<td>' . $row["mis_vp_approv"] . '</td>';
                        }   
                    }
                    if (is_null($row["assign_to"])){
                        if ($department_code == $row["project_department"] && !is_null($row["mis_vp_approv"]) && !is_null($row["mis_approv"]) && !is_null($row["department_approv"])){
                            if ($authorization <=2){
                                echo '<td><button type="button" class="btn btn-primary btn-sm">Assign</button></td>';
                            }else{
                                echo '<td><button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Claim Project Ownership" onclick="changeModalTitle(this)">Claim</button></td>';
                            }                     
                        }else{
                            echo '<td>Not Assigned</td>';
                        }                        
                    }else{
                        echo '<td>' . $row["assign_to"] . '</td>';
                    }
                    echo '</tr>';
                    $count += 1;
                }
            }
        } else {
                echo '<tr><td colspan="10">No project found.</td></tr>';
        }
        if ($count == 0){
            echo '<tr><td colspan="10">No project found.</td></tr>';
        }
        ?>
        </table>
    -->
     <h1>My Requests</h1>
    <div class="table-container" style="margin-bottom:50px">
        <table id="test-project-table">
        <tr class="thead-dark">
            <th>
            Date
            </th>
            <th>
            Project Name
            </th>
            <th>
            Description
            </th>
            <th>
            Status
            </th>
            <th>
            Proj. Dept.
            </th>
            <th>
            Need By
            </th>
            <th>
            Last Activity
            <span class="sort-icon"></span>
            </th>
            <th colspan='2' style='text-align:center'>
            Approvals
            </th>
            <th>
            Assigned to
            </th>                
        </tr>
    
        <?php       
        if ($result && $result->num_rows > 0) {   
            $count = 0;
            $result->data_seek(0);
            // Output each project detail as a table row
            while ($row = $result->fetch_assoc()) {
                if ($row['requestor_id'] == $id || str_contains($_SESSION['short_name'], $row["assign_to"])){
                    echo '<tr style="border-top:6px solid #ddd">';
                    echo '<td rowspan="5">' . $row["date"] . '</td>';
                    echo '<td rowspan="5" id="'.$row["id"].'"><a href="project_detail.php?id=' . $row["id"] . '" target="_blank">' . ucwords($row["project_name"]) . '</a></td>';                
                    echo '<td rowspan="5">' . $row["description"] . '</td>';
                    echo '<td rowspan="5">' . $row["status"] . '</td>';
                    echo '<td rowspan="5">' . $row["pd_name"] . '</td>';
                    echo '<td rowspan="5">' . $row["need_by_date"] . '</td>';
                    echo '<td rowspan="5"><a href="#" onclick="window.open('."'".'project_log.php?i='.$row["id"]."',''".",'width=1200,height=600')".'";>' . $row["last_act_date"] . '</a></td>';
                    echo '<td><b>Department Approval:</b></td>';
                    echo '<td>';
                    if ($row["department_approv"] == 'N'){
                        echo 'Not Required';
                    }else{
                        if (is_null($row["department_approv"])){
                            echo 'Pending';
                        }else{
                            echo $row["department_approv"];
                        }   
                    }
                    echo '</td>';
                    echo '<td rowspan="5">';
                    if (is_null($row["assign_to"])){
                        if ($department_code == $row["project_department"] && !is_null($row["mis_vp_approv"]) && !is_null($row["mis_approv"]) && !is_null($row["department_approv"])){
                            if ($authorization <=2){
                                echo '<button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Assign Employee" onclick="changeModalTitle(this)">Assign</button>';
                            }else{
                                echo '<button type="button" class="btn btn-primary btn-sm" data-toggle="modal" data-target="#modalBox" data-modal-title="Claim Project Ownership" onclick="changeModalTitle(this)">Claim</button>';
                            }                     
                        }else{
                            echo 'Not Assigned';
                        }                        
                    }else{
                        echo $row["assign_to"];
                    }
                    echo '</td>';
                    echo '</tr>';
                    echo '<tr></tr>';
                    echo '<tr>';
                    echo '<td><b>'.$row["pd_name"].' Approval:</b></td>';
                    echo '<td>';
                    if ($row["mis_approv"] == 'N' or $row["project_department"] == $department_code){
                        echo 'Not Required';
                    }else{
                        if (is_null($row["mis_approv"])){
                            echo 'Pending';
                        }else{
                            echo $row["mis_approv"];
                        }                       
                    }
                    echo '</td>';
                    echo '</tr>';
                    echo '<tr></tr>';
                    echo '<tr>';
                    echo '<td><b>'.$row["pd_name"].' VP Approval:</b></td>';
                    echo '<td>';
                    if ($row["mis_vp_approv"] == 'N'){
                        echo 'Not Required';
                    }else{
                        if (is_null($row["mis_vp_approv"])){
                            echo 'Pending';
                        }else{
                            echo $row["mis_vp_approv"];
                        }   
                    }
                    echo '</td>';
                    echo '</tr>';
                    $count += 1;
                }
            }
            if ($count == 0){
                echo '<tr><td colspan="10">No project found.</td></tr>';
            }
        } else {
                echo '<tr><td colspan="10">No project found.</td></tr>';
        }

        ?>
        </table>

        <a type='button' class='btn btn-info btn-sm m-3' href='index.php'>Go Back</a>
    </div>
    <!-- Modal -->
    <div class="modal fade" id="modalBox" tabindex="-1" role="dialog" aria-labelledby="modalBoxLabel" aria-hidden="true">
        <div class="modal-dialog" role="document">
            <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="modalBoxLabel">Modal Title</h5>
                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                <span aria-hidden="true">&times;</span>
                </button>
            </div>
            <form method="POST" action="<?php echo htmlspecialchars($_SERVER["PHP_SELF"]); ?>">                
                <div class="modal-body">   
                    <div class="form-group" id="assign_div" style="display:none">
                        <label for="assignment" id="assignment_label">Assign to:</label>
                        <i>Hold Ctrl to select multiple</i>
                        <select id="assignment" name="assignment[]" multiple>
                            <?php
                                while ($assignment = $employee->fetch_assoc()) {
                                    echo "<option value='".$assignment["id"]."'>" . $assignment["name"] . "</option>";
                                }
                            ?>
                        </select>
                    </div>  
                    <div class="form-group">
                        <label for="comment" id="comment_label">Comment:</label>
                        <textarea class="form-control" id="comment" name="comment" rows="4" required></textarea>
                    </div>         
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary btn-sm" data-dismiss="modal">Cancel</button>
                    <button id="submit_btn" type="submit" class="btn btn-primary">Submit</button>
                </div>
                <input type="hidden" id="action1" name="action1" value="">
                <input type="hidden" id="action2" name="action2" value="">
                <input type="hidden" id="submit_id" name="submit_id" value="">
            </form>
            </div>
        </div>
    </div>
<script>
  var sortColumn = -1;
  var sortDirection = 'asc';

  function changeModalTitle(ele) {
      var title = ele.getAttribute('data-modal-title');
      var modalTitle = document.getElementById('modalBoxLabel');
      modalTitle.textContent = title;
      document.getElementById('action1').value = title;
      document.getElementById('action2').value = ele.innerText;
      if (ele.innerText == "Approve" || ele.innerText == "Assign"){
        document.getElementById('comment').removeAttribute("required");
        document.getElementById('comment_label').innerText = "Comment:";
        if (ele.innerText == "Assign"){
            document.getElementById('assign_div').style.display = 'block';
            document.getElementById('assignment').setAttribute("required",true);
        }else{
            document.getElementById('assignment').removeAttribute("required");
            document.getElementById('assign_div').style.display = 'none';
        }
      }else{
        document.getElementById('comment_label').innerText = "*Comment:";
        document.getElementById('comment').setAttribute("required",true);
        document.getElementById('assignment').removeAttribute("required");
        document.getElementById('assign_div').style.display = 'none';
      }
      document.getElementById('submit_id').value = ele.parentNode.parentNode.childNodes[1].getAttribute('id');
      document.getElementById('submit_btn').innerText = ele.innerText;
      document.getElementById('submit_btn').className = ele.className;
  }

  function sortTable(columnIndex,ele) {
    var table, rows, switching, i, x, y, shouldSwitch, direction, switchcount = 0;
    table_id = ele.parentNode.parentNode.parentNode.getAttribute('id');
    table = document.getElementById(table_id);
    switching = true;
    direction = sortDirection === 'asc' ? 'desc' : 'asc';

    // Reset sort icons
    var sortIcons = table.getElementsByClassName('sort-icon');
    for (var i = 0; i < sortIcons.length; i++) {
      sortIcons[i].innerHTML = '';
    }

    sortColumn = columnIndex;
    sortDirection = direction;

    while (switching) {
      switching = false;
      rows = table.rows;

      for (i = 1; i < (rows.length - 1); i++) {
        shouldSwitch = false;
        x = rows[i].getElementsByTagName("TD")[columnIndex];
        y = rows[i + 1].getElementsByTagName("TD")[columnIndex];

        if (direction === "asc") {
          if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
            shouldSwitch = true;
            break;
          }
        } else if (direction === "desc") {
          if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
            shouldSwitch = true;
            break;
          }
        }
      }

      if (shouldSwitch) {
        rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
        switching = true;
        switchcount++;
      }
    }

    // Update sort icon
    var sortIcon = table.getElementsByClassName('sort-icon')[columnIndex];
    sortIcon.innerHTML = direction === 'asc' ? '&#9650;' : '&#9660;';
    sortIcon.classList.add(direction === 'asc' ? 'asc' : 'desc');

  }
</script>

<script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/popper.js@1.14.7/dist/umd/popper.min.js" integrity="sha384-UO2eT0CpHqdSJQ6hJty5KVphtPhzWj9WO1clHTMGa3JDZwrnQq4sF86dIHNDz0W1" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@4.3.1/dist/js/bootstrap.min.js" integrity="sha384-JjSmVgyd0p3pXB1rRibZUAYoIIy6OrQ6VrjIEaFf/nJGzIxFDsf4x0xIM+B07jRM" crossorigin="anonymous"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
