<?php
    require('validate.php');
    $id = $_SESSION['id'];
    require('connection.php');
    // Check the connection
    if ($conn->connect_error) {
        die("Connection failed: " . $conn->connect_error);
    }
    $project_id = isset($_GET['i']) ? $_GET['i'] : '';
    if (empty($project_id)){
        header('Location: error.php');
    }else{
        $project_id = intval($project_id); 
    }
    $sql = "SELECT 
                p.project_name,
                o.name,
                pl.description,
                e.name as add_by,
                pl.add_date,
                gc.comment
            FROM 
                project_log pl 
            LEFT JOIN 
                options o 
            ON 
                o.id=pl.type  
            LEFT JOIN
                projects p
            ON
                p.id=pl.project
            LEFT JOIN
                employee e
            ON
                e.id=pl.add_by
            LEFT JOIN
                general_comment gc
            ON
                gc.subject = 23
                AND gc.subject_id = pl.id
            WHERE 
                project=".$project_id." 
            ORDER BY 
                add_date desc";
    $result = mysqli_query($conn, $sql);
    if (!($result && mysqli_num_rows($result) > 0)){
        header('Location: error.php');
    }
    // Close the database connection
    $conn->close();
    $row = mysqli_fetch_assoc($result);
    $project_name = $row['project_name'];
?>
<!DOCTYPE html>
<html>
<head>
  <title>Project Log</title>  
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.3.1/dist/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">  
  <link rel="stylesheet" href="style.css">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <?php    
        echo "<h1>Project '".$project_name."' Log</h1>";      
        $result->data_seek(0);
    ?>
    <div class="table-container" style="margin-bottom:50px">
        <table id="project-table" class="table_hover">
            <tr>
                <th>Type</th>
                <th>Description</th>
                <th>Comment</th>
                <th>Added By</th>
                <th>Date</th>
            </tr>
            <?php while ($row = mysqli_fetch_assoc($result)) { ?>
                <tr>
                    <td><?php echo $row['name']; ?></td>
                    <td><?php echo $row['description']; ?></td>
                    <td><?php echo $row['comment']; ?></td>
                    <td><?php echo $row['add_by']; ?></td>
                    <td><?php echo $row['add_date']; ?></td>
                </tr>
            <?php } ?>
        </table>
        <a type='button' class='btn btn-danger btn-sm m-3' href='#' onclick="window.close()">Close</a>
    </div>
</body>
</html>